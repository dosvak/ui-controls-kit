#!/usr/bin/env python3
"""twxkit - build an importable IBM BAW / BPM process application package (TWX) from a Python description.

Self-contained: Python 3 standard library only, no base export, no toolkit zips. The package declares its two dependencies
(System Data, UI Toolkit) by the ids every 8.6.x / BAW 2x server carries; the importer binds the server's own copies.
Verified: a package written this way imports through the Process Center console on BPM 8.6.2 and on BAW 26.0.0.0
(Workflow Center) and its dashboard plays back without errors; on CP4BA the importer rebinds System Data itself.

What it renders (every object in the exact XML shape of a Process Center export, ids deterministic = uuid5 in the app namespace):
  project defaults (63.), environment variable set (62.), business objects (12.), teams (24.), server / web files (61. + files/),
  service flows (1., processType 12: script tasks, nested calls, exclusive gateways, loops), client-side human services
  (1., processType 10: coach built from UI Toolkit controls, optional server-side initialisation flow, exposed as a dashboard),
  optional coach views (64., inline JavaScript / CSS / HTML, options, binding), META-INF/package.xml + metadata.xml + MANIFEST.MF.

Minimal use:
    import twxkit as k
    app = k.App('Kit Sample', 'KITSMP', '1.0', 'what it does')
    app.env('serverBaseURL', 'https://localhost:9443', 'REST base URL as seen from the server')
    app.bo('KSResult', [('ok', 'Boolean'), ('message', 'String'), ('rows', 'KSRow[]')])
    app.flow('KS Echo', inputs=[('data', 'KSQuery')], outputs=[('results', 'KSResult')], script=JS)
    app.cshs('Kit Dashboard', variables=[('criteria', 'KSQuery', 'new'), ('result', 'KSResult')], init='KS Init',
             layout=lambda L: [L.text('Query', 'Text', 'tw.local.criteria.text'), L.button('Run', 'Run', '${SvcEcho}.execute();'),
                               L.service('SvcEcho', 'KS Echo', 'tw.local.criteria', 'tw.local.result'), L.table('Rows', 'Rows', 'tw.local.result.rows', [('name', 'Name')])])
    app.write('Kit-Sample-1.0.twx')      # + Kit-Sample-1.0.ids.json (app / branch / snapshot / flow / dashboard ids)

Rules the engine enforces (all verified, see the knowledge topic "twx-from-scratch"): a Service Call control needs the flow's input
named `data` and its output `results`; environment variables need non-empty defaults; scripts must use declared variable names
exactly; event expressions must not contain backslashes; option labels stay short; layout item ids are unique per coach;
a flow started from a coach must be Ajax exposed and referenced by the dashboard (a Service Call control is enough).
"""
import hashlib, json, os, re, uuid, zipfile, datetime
import xml.etree.ElementTree as ET

# ------------------------------------------------------------------------------------------------------ product constants
# System Data and UI Toolkit as installed on BPM 8.6.x and BAW 20-26 (same ids on 8.6.2 and 26.0.0.0; listed by GET /rest/bpm/wle/v1/toolkit)
SYSDATA = dict(project='2066.1b351583-e5cb-43b7-baee-340a63130ea7', branch='2063.0798815e-0346-4ef4-8946-ab4301c9f340',
               snapshot='2064.1080ded6-d153-4654-947c-2d16fce170ed', name='System Data', acronym='TWSYS', version='8.6.0.0',
               created='2015-08-24T20:00:00.000-04:00')
SYSDATA_TC_SNAPSHOT = '2064.1080ded6-d153-4654-947c-2d16fce170db'   # the "8.6.0.0_TC" variant (the tip on BAW 26 Workflow Center); either imports
UITK = dict(project='2066.ec5973da-aebe-40f6-aa02-a77962288f52', branch='2063.83ee2bb2-72b4-4a4d-b8ae-37ecd983c05e',
            snapshot='2064.304ac881-16c3-47d2-97d5-6e4c4a893177', name='UI Toolkit', acronym='SYSBPMUI', version='8.6.0.0',
            created='2017-05-24T19:23:53.574-04:00')
# System Data types (id part after the dependency prefix)
TYPES = {'String': '12.db884a3c-c533-44b7-bb2d-47bec8ad4022', 'Integer': '12.3fa0d7a0-828a-4d60-99cc-db5ed143fc2d',
         'Decimal': '12.536b2aa5-a30f-4eca-87fa-3a28066753ee', 'Boolean': '12.83ff975e-8dbc-42e5-b738-fa8bc08274a2',
         'Date': '12.68474ab0-d56f-47ee-b7e9-510b45a2a8be', 'Time': '12.20fdb1a2-f6ec-462e-8627-d49859ba42ae',
         'ANY': '12.c09c9b6e-aabd-4897-bef2-ed61db106297', 'Map': '12.90c5b1d3-3fa1-4b3b-ab27-220b0652dc55',
         'NameValuePair': '12.d2e5a15a-ea53-4793-9e93-29af5bd80b13', 'Record': '12.07e8bc37-eb9d-42a2-9863-9212ce153191',
         'XMLDocument': '12.4715ae70-6fe9-4d51-a010-20ddb068bcdb', 'XMLElement': '12.8a176cc2-eebb-4310-a9c7-9bc62b3a8002',
         'XMLNodeList': '12.c93cbe57-28b9-4b8c-a7a7-e8c77b734ace', 'URL': '12.010f99b3-dd03-4f3d-938f-55f109a8bbb7',
         'Team': '12.4f114e73-2520-40d7-b2ea-db9dcc4aa1f0', 'IndexedMap': '12.f2883d4c-0f90-43d8-9adb-32b75b555fb7',
         'SQLResult': '12.3b1e3757-a1f4-4c3f-bbb8-16fecd4d65c1', 'SQLParameter': '12.f453f500-ca4e-4264-a371-72c1892e8b7c',
         'DocumentFile': '12.e9d8a76b-6dba-4316-80e0-d6ac49366c82', 'CaseReference': '12.a4cf6da6-206a-43e9-bf8d-30d779844800'}
# UI Toolkit types (referenced through the UI Toolkit dependency): the chart data contract and the sensor / geo records
UITK_TYPES = {'DataSeries': '12.63a604e8-e026-4605-aae1-272b67822cc7', 'DataPoint': '12.db7aaff9-c0a7-4f62-80e7-4329dd49f4c2',
              'DeviceInfo': '12.9ff0c19f-7322-4dee-9264-824e2c2371ec', 'GeoLocation': '12.6632ee5b-4a41-4935-bb5e-3b09f8c3cf8f',
              'StreetAddress': '12.53cf0411-8c1d-454c-ab08-74eeb9d5a060', 'LatLong': '12.5cc4a08f-5502-43a3-9259-ae44bdb8cada'}
TEAM_ALL_USERS = '24.da7e4d23-78cb-4483-98ed-b9c238308a03'   # System Data "All Users"
TEAM_SYSTEM = '24.6fd38d02-81cf-48ab-bd42-8ff4c0a1628b'      # System Data "System" (lane of service flows)
THEME_CLASSIC = '72.e77f2a7e-10b4-45ee-90eb-e5b1546cc743'    # System Data theme "Classic"
THEME_CARBON = '72.993e03e9-2574-40fc-807c-65b06be378fd'     # System Data theme "Carbon"
THEMES = {'classic': THEME_CLASSIC, 'carbon': THEME_CARBON}
# UI Toolkit 8.6.0.0 coach views (name -> id); the same ids on BAW 26
VIEWS = {'Alerts': '64.e6b70dd5-4d8e-4598-a08b-dcb9a9dfaba5', 'Area Chart SDS': '64.2c8ffc35-7cea-4d7b-85d9-e3d02a901bea', 'Badge': '64.dbd042c3-8328-49af-9f0b-a92ba4ffb841',
         'Bar Chart SDS': '64.8d17dda8-175c-49ec-aaa8-cba00f7b5c24', 'Breadcrumbs': '64.281a0d61-afa8-4297-bbc8-29a2d1c1bc83', 'Button': '64.7133c7d4-1a54-45c8-89cd-a8e8fa4a8e36',
         'Caption Box': '64.49c8e80a-9836-44d3-a3a7-97968fc8b4cb', 'Checkbox Group': '64.b00a9c90-0931-47ac-ab7c-e9fd9b891ccb', 'Checkbox': '64.fffd1628-baee-44e8-b7ca-5ae48644b0be',
         'Collapsible Panel': '64.aa70e5b9-aade-4334-b92d-1fb5e61f4b0a', 'Configuration': '64.a87aa2c7-c36c-4ee8-9b04-c296503ffb15', 'Data Export': '64.90bf9818-cbe7-4435-842a-8ae4559a376c',
         'Data': '64.9b679256-e93b-4400-89f2-bd15b0c5578d', 'Date Picker': '64.aeae8953-9e72-411e-b35a-93c7ab827c5c', 'Date Time Picker': '64.54643ff2-8363-4976-bb5e-d4eb1094cca3',
         'Decimal': '64.e0ede0f2-f3af-408c-af7b-e7a58eb5e2b4', 'Default Inline User Task Template': '64.dc5fd75e-5b13-460c-8cb8-1e463c729751', 'Deferred Section': '64.9ee7a0fd-5b25-497d-85fc-1cc09795f524',
         'Device Sensor': '64.14d6d2be-5be6-48f5-8fd7-949f575c6150', 'Donut Chart SDS': '64.0eeb7300-7ef8-4079-b3d2-d10ec7379e58', 'Event Subscription': '64.38adbdb0-9f2a-47d1-ac5e-27ca6946ad2e',
         'Exit Safeguard': '64.06a9923f-f2b5-41ff-aeec-257b7d61b29b', 'Geo Coder': '64.bfd6fc27-0b2b-4169-8970-7cb3b382d97f', 'Geo Location': '64.e302f8ff-4f48-4730-8a38-a04523ed8b15',
         'Horizontal Layout': '64.44f463cc-615b-43d0-834f-c398a82e0363', 'Horizontal Split': '64.5c490b0f-ce12-4f65-a959-6084ee570480', 'Icon': '64.1b440a6c-8508-4f95-bc28-728a58f2353c',
         'Image': '64.49422be7-d203-44dc-951d-7ca4361d7b94', 'Input Group': '64.33c2011d-5bc9-4609-9e48-0f42b858f1a0', 'Integer': '64.a6946c4c-f73d-4ced-9216-90018985ca96',
         'Line Chart SDS': '64.d11572b6-d14b-4267-9eea-98c6709a7dbb', 'Line': '64.ff97945c-a44b-44d1-8b36-083255daf920', 'Link': '64.22f864a3-15ab-48ce-9744-14f01b4b2368',
         'Map': '64.4e6c49be-c45f-4571-9e67-1d17ed36b1df', 'Masked Text': '64.b9c128d5-1c54-4a0a-9b76-0e7ffd6ed2a1', 'Modal Alert': '64.066607d7-6101-4ae6-aa5e-4b8fbbb433a7',
         'Modal Section': '64.66286dff-19bf-447a-ad5c-4fc385fea67d', 'Multi Purpose Chart': '64.c025cd95-70c4-4b5e-924a-7bf69174e123', 'Multi Select': '64.7df3f465-dc52-4d4a-88a1-8d237a5ca563',
         'Navigation Event': '64.ecaae891-b5b0-4836-bc25-def71fcad690', 'Note': '64.32441394-ff38-4ecb-8028-02fc04725fe9', 'Notification': '64.84561e27-ec84-49d3-adb9-de8e060437f0',
         'OpenLayers API': '64.d156e24b-e70a-4ffe-80f4-3153048db5cd', 'Output Text': '64.f634f22e-7800-4bd7-9f1e-87177acfb3bc', 'Panel Footer': '64.7f521ba9-7450-4ed7-98e3-a0128c2900c9',
         'Panel Header': '64.23384625-cb80-4295-899a-943504b7aaa1', 'Panel': '64.455e44ab-b77b-4337-b3f9-435e234fb569', 'Password': '64.4da8dcb3-7881-4e0f-8382-4e608751ce2e',
         'Pie Chart SDS': '64.ded8f8bd-32de-4fbb-89c6-a335368ea435', 'Places': '64.70e410ee-c257-456d-b8a0-051a5c9259cc', 'Popup Menu': '64.c0514f65-f0be-441c-88b7-efcd91e36389',
         'Progress Bar': '64.8f6a9870-14fb-474b-99c6-0e3844e23d67', 'QR Code': '64.32f56581-ee59-45d0-b58e-ed47e8a4d7bb', 'Radio Button Group': '64.bdddb841-6b07-4c08-bb5c-236a8da26b6a',
         'Radio Button': '64.ad2b879f-ee68-4bc9-9b1b-fb7c0856a48e', 'Responsive Sensor': '64.aa08832f-4366-4941-b213-3c1148b59d32', 'Service Call': '64.1feaead9-b1d2-4a7e-80a3-22156e6fe8f9',
         'Service Data Table': '64.6b29c1bc-c211-43ce-8fbc-904e6e4d57f7', 'Signature': '64.a62e7774-259f-4e17-914d-97daaf7a7a28', 'Single Select': '64.fd4da558-40d8-47be-92ca-c305708dc7b7',
         'Slider': '64.5a0a8518-8377-4232-ada1-9a2eaea7f7f7', 'Spacer': '64.71b97b55-fda9-48e8-b21b-58fb4e85ca10', 'Stack': '64.05d9d0b5-0423-4ab6-b16c-e3554dfaf4a6',
         'Status Box': '64.c48318be-0720-43d9-9c02-7fe15244ab79', 'Step Chart SDS': '64.2a8c9084-e5f5-4be3-a15c-1dfbd5f5c109', 'Style': '64.50e886c4-eede-4bba-9b9a-2f6b51ce6a9b',
         'Switch': '64.bff9f5ff-fea4-4a70-87a5-769301740798', 'Tab Section': '64.c05b439f-a4bd-48b0-8644-fa3b59052217', 'Table Layout Cell': '64.5aea8d13-714d-4d05-8717-8c744b419365',
         'Table Layout Row': '64.9ac7d257-d8ad-47e6-a1df-b76cf1a4ec87', 'Table Layout': '64.bd961fbd-60cd-4341-9234-cec3516a5ed8', 'Table': '64.f515b79f-fe61-4bd3-8e26-72f00155d139',
         'Text Area': '64.0e61869e-73fd-4401-b156-8c11adaec3f8', 'Text Editor': '64.8881a0d8-ba85-4a8a-9c3b-c2f8ab32ece9', 'Text Reader': '64.933fd33b-4cce-4f8d-8219-7bac494f200d',
         'Text': '64.5663dd71-ff18-4d33-bea0-468d0b869816', 'Timer': '64.ec19f655-f26d-45a2-a488-6f73536a03eb', 'Tooltip': '64.dc7cb757-a065-44c1-a92d-d186f8eea4e2',
         'Type Ahead Text': '64.847f8ace-ae59-47ef-9b55-e5a4242e7426', 'Variant': '64.b9738f74-c1ec-4483-90e0-e2dd133e4608', 'Vertical Layout': '64.ef447b87-24a2-42a7-b2b9-cd471e9f7b67',
         'Video': '64.90af4be1-268b-4bef-8e3d-627a1f3b76ed', 'Well': '64.64ae2c6c-6c21-491c-b5ab-c58848dd9e48'}
NOW = 1545000743114
BPMN_NS = ('xmlns:ns17="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:ns2="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/case" '
           'xmlns:ns3="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process" xmlns:ns4="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/wle" '
           'xmlns:ns5="http://www.ibm.com/bpm/Extensions" xmlns:ns6="http://www.ibm.com/xmlns/prod/bpm/uca" xmlns:ns7="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/trackinggroup" '
           'xmlns:ns8="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/team" xmlns:ns9="http://www.ibm.com/xmlns/bpmnx/20100524/v1/BusinessVocabulary" '
           'xmlns:ns10="http://www.omg.org/spec/DD/20100524/DI" xmlns:ns11="http://www.omg.org/spec/DD/20100524/DC" xmlns:ns12="http://www.omg.org/spec/BPMN/20100524/BPMNDI" '
           'xmlns:ns13="http://www.ibm.com/xmlns/prod/bpm/graph" xmlns:ns14="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/auth" '
           'xmlns:ns15="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/extservice" xmlns:ns16="http://www.ibm.com/xmlns/links" xmlns:ns18="http://www.ibm.com/bpm/CoachDesignerNG" '
           'xmlns:ns19="http://www.ibm.com/xmlns/tagging" xmlns:ns20="http://www.ibm.com/bpm/uitheme" xmlns:ns21="http://www.ibm.com/bpm/coachview"')

# ---- business process (BPD, 25.) fragments of an 8.6.2 export: BPMN namespace declarations and the office block (fixed text)
BPD_DEFS_OPEN = ('<ns16:definitions xmlns:ns16="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:ns2="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/case" '
                 'xmlns:ns3="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process" xmlns:ns4="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/wle" xmlns:ns5="http://www.ibm.com/bpm/Extensions" '
                 'xmlns:ns6="http://www.ibm.com/xmlns/prod/bpm/uca" xmlns:ns7="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/trackinggroup" xmlns:ns8="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/team" '
                 'xmlns:ns9="http://www.ibm.com/xmlns/bpmnx/20100524/v1/BusinessVocabulary" xmlns:ns10="http://www.omg.org/spec/DD/20100524/DI" xmlns:ns11="http://www.omg.org/spec/DD/20100524/DC" '
                 'xmlns:ns12="http://www.omg.org/spec/BPMN/20100524/BPMNDI" xmlns:ns13="http://www.ibm.com/xmlns/prod/bpm/graph" xmlns:ns14="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/extservice" '
                 'xmlns:ns15="http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/auth" xmlns:ns17="http://www.ibm.com/bpm/CoachDesignerNG" xmlns:ns18="http://www.ibm.com/xmlns/links" '
                 'xmlns:ns19="http://www.ibm.com/bpm/uitheme" xmlns:ns20="http://www.ibm.com/bpm/coachview" xmlns:ns21="http://www.ibm.com/xmlns/tagging" '
                 'id="%s" targetNamespace="" expressionLanguage="http://www.ibm.com/xmlns/prod/bpm/expression-lang/javascript">')
BPD_OFFICE = ('<officeIntegration><sharePointParentSiteDisabled>true</sharePointParentSiteDisabled><sharePointParentSiteName>&lt;#= tw.system.process.name #&gt;</sharePointParentSiteName>'
              '<sharePointParentSiteTemplate>ParentSiteTemplate.stp</sharePointParentSiteTemplate><sharePointWorkspaceSiteName>&lt;#= tw.system.process.name #&gt; &lt;#= tw.system.process.instanceId #&gt;</sharePointWorkspaceSiteName>'
              '<sharePointWorkspaceSiteDescription>This site has been automatically generated for managing collaborations and documents for the process instance: &lt;#= tw.system.process.name #&gt; &lt;#= tw.system.process.instanceId #&gt;</sharePointWorkspaceSiteDescription>'
              '<sharePointWorkspaceSiteTemplate>WorkspaceSiteTemplate.stp</sharePointWorkspaceSiteTemplate><sharePointLCID>1033</sharePointLCID></officeIntegration>')
# Diagram geometry the designer uses (pixels): node boxes, lane stacking, column spacing of the automatic layout
BPD_SIZE = {'start': (24, 24), 'end': (24, 24), 'timer': (24, 24), 'boundary': (24, 24), 'gateway': (32, 32), 'parallel': (32, 32), 'script': (95, 70), 'service': (95, 70), 'user': (95, 70)}
BPD_LANE_HEIGHT = 150; BPD_COLUMN = 150; BPD_LEFT = 60

def esc(s): return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\r', '&#xD;')
def attr(s): return esc(s).replace('"', '&quot;')
def own_version(xml):
    """Match of the object's own <versionId> (a direct child of the root object element, 8-space indentation): parameter / variable blocks
    that precede it in export order (bpdParameter, processParameter) carry their own versionIds and must not be mistaken for it."""
    m = re.search(r'\n        <versionId>([^<]*)</versionId>', xml)
    return m or re.search(r'<versionId>([^<]*)</versionId>', xml)

def legacy_guid(u):
    """guid:<16 hex>:<8 hex>:<8 hex>:-<4 hex> shaped identifier derived from a uuid (legacy item guids)."""
    h = u.replace('-', ''); return f'guid:{h[:16]}:{h[16:24]}:{h[24:32]}:-{h[:4]}'

# Config options and content boxes declared by every UI Toolkit view above (read from the toolkit's coach view definitions):
# option -> "<L>O|E|S:<type>" (L = list option, O = object option, E = event, S = service; type String / Boolean / Integer / enum / ANY).
# A config option the view does not declare makes the coach generator answer 500 at playback ("Unable to load generatecoachng"), so
# Layout.ref() refuses it at build time. Responsive values ({"isResponsiveData": ...}) are for String / Boolean / Integer options.
VIEW_OPTIONS = {
    'Alerts': ({'alertTopics': 'LO:String', 'autoFadeDelay': 'O:Integer', 'alertColorStyle': 'O:enum', 'darkStyle': 'O:Boolean', 'dense': 'O:Boolean', 'animate': 'O:Boolean', 'eventON_ALERTCLICK': 'E:String', 'eventON_ALERTCLOSE': 'E:String', 'eventON_ALERTEXPIRED': 'E:String', 'showIcon': 'O:Boolean'}, ()),
    'Area Chart SDS': ({'dataMode': 'O:enum', 'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'enableMenu': 'O:Boolean', 'maxYAxisTicks': 'O:Integer', 'yAxisTickPrecision': 'O:Integer', 'minYAxisValue': 'O:enum', 'maxYAxisValue': 'O:enum', 'xAxisCulling': 'O:Boolean', 'maxXTickCount': 'O:Integer', 'showTooltip': 'O:Boolean', 'splineArea': 'O:Boolean', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'O:enum', 'showValueLabels': 'O:Boolean', 'showBreadCrumbs': 'O:Boolean', 'pointSize': 'O:enum', 'xyAxisColorStyle': 'O:enum', 'horizontalGridlineStyle': 'O:enum', 'xLabelRotation': 'O:enum', 'xAxisHeight': 'O:Integer', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Badge': ({'expression': 'E:String', 'colorStyle': 'O:enum', 'shapeStyle': 'O:enum', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ()),
    'Bar Chart SDS': ({'dataMode': 'O:enum', 'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'enableMenu': 'O:Boolean', 'maxYAxisTicks': 'O:Integer', 'yAxisTickPrecision': 'O:Integer', 'minYAxisValue': 'O:enum', 'maxYAxisValue': 'O:enum', 'xAxisCulling': 'O:Boolean', 'maxXTickCount': 'O:Integer', 'showTooltip': 'O:Boolean', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'O:enum', 'showValueLabels': 'O:Boolean', 'showBreadCrumbs': 'O:Boolean', 'xyAxisColorStyle': 'O:enum', 'horizontalGridlineStyle': 'O:enum', 'xLabelRotation': 'O:enum', 'xAxisHeight': 'O:Integer', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Breadcrumbs': ({'eventON_LOAD': 'E:String', 'eventON_ITEM_CLICK': 'E:String'}, ()),
    'Button': ({'expression': 'E:String', 'tabIndex': 'O:Integer', 'preventMultipleClicks': 'O:Boolean', 'colorStyle': 'O:enum', 'shapeStyle': 'O:enum', 'sizeStyle': 'O:enum', 'outline': 'O:Boolean', 'icon': 'O:String', 'width': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_BOUNDARYEVT': 'E:String', 'iconLocation': 'O:enum', 'ghostMode': 'O:Boolean'}, ()),
    'Caption Box': ({'expression': 'E:String', 'width': 'O:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'labelHorizAlign': 'O:enum', 'labelVertAlign': 'O:enum', 'shrinkToContent': 'O:Boolean', 'labelColorStyle': 'O:enum', 'labelSizeStyle': 'O:enum', 'labelWeightStyle': 'O:enum', 'eventON_LOAD': 'E:String'}, ('ContentBox1',)),
    'Checkbox': ({'tabIndex': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String'}, ()),
    'Checkbox Group': ({'itemLookupMode': 'O:enum', 'itemService': 'S:enum', 'inputData': 'O:ANY', 'itemList': 'LO:ANY', 'staticList': 'LO:enum', 'dataMapping': 'O:enum', 'width': 'O:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_SVCITEMS': 'E:String', 'eventON_SVCERROR': 'E:String', 'eventON_CHANGE': 'E:String', 'tabIndex': 'O:String'}, ()),
    'Collapsible Panel': ({'expression': 'E:String', 'initiallyCollapsed': 'O:Boolean', 'panelGroup': 'O:String', 'colorStyle': 'O:enum', 'width': 'O:String', 'height': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_EXPAND': 'E:String', 'eventON_COLLAPSE': 'E:String'}, ('ContentBox1',)),
    'Configuration': ({'debugging': 'O:Boolean', 'showLog': 'O:Boolean', 'lastFirst': 'O:Boolean', 'parameters': 'LO:enum', 'globalTextDir': 'O:enum', 'locale': 'O:String', 'i18nService': 'S:enum'}, ()),
    'Data': ({'expression': 'E:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String'}, ()),
    'Data Export': ({'tableName': 'O:String', 'fileType': 'O:enum', 'defName': 'O:String', 'colNames': 'O:Boolean', 'tabIndex': 'O:Integer', 'inclInvis': 'O:Boolean', 'colSpecs': 'LO:enum', 'colHeaders': 'LO:String', 'colOrder': 'LO:String', 'colorStyle': 'O:enum', 'shapeStyle': 'O:enum', 'sizeStyle': 'O:enum', 'outline': 'O:Boolean', 'icon': 'O:String', 'width': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_CELLEXPT': 'E:String'}, ()),
    'Date Picker': ({'type': 'O:enum', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:String', 'format': 'O:String', 'placeHolder': 'O:String', 'weekStart': 'O:enum', 'startDate': 'O:String', 'endDate': 'O:String', 'disabledWeekDays': 'O:enum', 'startView': 'O:enum', 'minViewMode': 'O:enum', 'enableTodayButton': 'O:Boolean', 'enableClearButton': 'O:Boolean', 'orientation': 'O:enum', 'colorStyle': 'O:enum', 'showWeeks': 'O:Boolean', 'noAutoclose': 'O:Boolean', 'highlightToday': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_BEFORE_SHOW_DAY': 'E:String'}, ()),
    'Date Time Picker': ({'type': 'O:enum', 'customPickerOnly': 'O:Boolean', 'includeTimePicker': 'O:Boolean', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'calendarType': 'O:enum', 'tabIndex': 'O:String', 'format': 'O:String', 'placeHolder': 'O:String', 'weekStart': 'O:enum', 'startDate': 'O:enum', 'endDate': 'O:enum', 'disabledWeekDays': 'O:enum', 'blackoutDates': 'LO:enum', 'blackoutDateStart': 'O:enum', 'blackoutDateEnd': 'O:enum', 'startView': 'O:enum', 'minViewMode': 'O:enum', 'enableTodayButton': 'O:Boolean', 'enableClearButton': 'O:Boolean', 'orientation': 'O:enum', 'colorStyle': 'O:enum', 'showWeeks': 'O:Boolean', 'noAutoclose': 'O:Boolean', 'highlightToday': 'O:Boolean', 'hideHeader': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_BEFORE_SHOW_DAY': 'E:String', 'enableCalendarIcon': 'O:Boolean', 'yearSelectorStyle': 'O:enum'}, ()),
    'Decimal': ({'expression': 'E:String', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'decimalSep': 'O:String', 'prefix': 'O:String', 'postfix': 'O:String', 'numericFormatting': 'O:enum', 'thousandsSep': 'O:String', 'hideThousandsSeparator': 'O:Boolean', 'decimalPlaces': 'O:Integer', 'currency': 'O:enum', 'currencySymbol': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String', 'eventON_FORMAT': 'E:String'}, ()),
    'Default Inline User Task Template': ({'inputMessage': 'O:String', 'outputMessage': 'O:String', 'inputOutputMessage': 'O:String'}, ('ContentBox1',)),
    'Deferred Section': ({'autoLoad': 'O:Boolean', 'autoLoadDelay': 'O:Integer', 'eventON_SECLOAD': 'E:String'}, ('ContentBox1',)),
    'Device Sensor': ({'eventON_LOAD': 'E:String'}, ()),
    'Donut Chart SDS': ({'dataMode': 'O:enum', 'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'enableMenu': 'O:Boolean', 'showTooltip': 'O:Boolean', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'LO:enum', 'showBreadCrumbs': 'O:Boolean', 'legendPlacement': 'O:enum', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Event Subscription': ({'eventName': 'O:String', 'eventON_EVENT': 'E:String'}, ()),
    'Exit Safeguard': ({'challengeByDefault': 'O:Boolean', 'message': 'O:String'}, ()),
    'Geo Coder': ({'location': 'O:enum', 'eventON_LOAD': 'E:String', 'eventON_ADDRESSREQ': 'E:String', 'eventON_ADDRESS': 'E:String', 'eventON_ADDRESSERR': 'E:String'}, ()),
    'Geo Location': ({'monitoringMode': 'O:enum', 'highAccuracy': 'O:Boolean', 'geoTimeout': 'O:Integer', 'maxAge': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_LOCINFOREQ': 'E:String', 'eventON_LOCINFO': 'E:String', 'eventON_LOCINFOERR': 'E:String'}, ()),
    'Horizontal Layout': ({'layoutFlow': 'O:enum', 'hAlignment': 'O:enum', 'vAlignment': 'O:enum', 'width': 'O:String', 'height': 'O:String', 'startEmpty': 'O:Boolean', 'sensor': 'O:String', 'behaviors': 'LO:enum', 'deferLoad': 'O:Boolean', 'loadBatchSize': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_RESUPD': 'E:String'}, ('ContentBox1',)),
    'Horizontal Split': ({'height': 'O:String', 'paneSpecs': 'LO:enum', 'eventON_LOAD': 'E:String', 'eventON_COLLAPSE': 'E:String', 'eventON_EXPAND': 'E:String'}, ('ContentBox1',)),
    'Icon': ({'preventMultipleClicks': 'O:Boolean', 'showAsIcon': 'O:Boolean', 'colorStyle': 'O:enum', 'iconSize': 'O:String', 'outline': 'O:Boolean', 'icon': 'O:String', 'radius': 'O:String', 'size': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_BOUNDARYEVT': 'E:String'}, ()),
    'Image': ({'preventMultipleClicks': 'O:Boolean', 'urlType': 'O:enum', 'appAcronym': 'O:String', 'defaultURL': 'O:String', 'defaultURLType': 'O:enum', 'defaultAppAcronym': 'O:String', 'radius': 'O:String', 'width': 'O:String', 'height': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ()),
    'Input Group': ({'width': 'O:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'buttonColorStyle': 'O:enum', 'buttonLocation': 'O:enum', 'buttonKind': 'O:enum', 'buttonInfo': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ('ContentBox1',)),
    'Integer': ({'expression': 'E:String', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'prefix': 'O:String', 'postfix': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String', 'eventON_FORMAT': 'E:String', 'numericFormatting': 'O:enum', 'thousandsSep': 'O:String', 'hideThousandsSeparator': 'O:Boolean'}, ()),
    'Line': ({}, ()),
    'Line Chart SDS': ({'dataMode': 'O:enum', 'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'enableMenu': 'O:Boolean', 'maxYAxisTicks': 'O:Integer', 'yAxisTickPrecision': 'O:Integer', 'minYAxisValue': 'O:enum', 'maxYAxisValue': 'O:enum', 'xAxisCulling': 'O:Boolean', 'maxXTickCount': 'O:Integer', 'showTooltip': 'O:Boolean', 'spline': 'O:Boolean', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'O:enum', 'showValueLabels': 'O:Boolean', 'showBreadCrumbs': 'O:Boolean', 'pointSize': 'O:enum', 'xyAxisColorStyle': 'O:enum', 'horizontalGridlineStyle': 'O:enum', 'xLabelRotation': 'O:enum', 'xAxisHeight': 'O:Integer', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Link': ({'expression': 'E:String', 'tabIndex': 'O:Integer', 'linkText': 'O:String', 'preventMultipleClicks': 'O:Boolean', 'linkType': 'O:enum', 'linkURL': 'O:String', 'sameWindow': 'O:Boolean', 'width': 'O:String', 'textAlignment': 'O:enum', 'colorStyle': 'O:enum', 'sizeStyle': 'O:enum', 'weightStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_BOUNDARYEVT': 'E:String'}, ()),
    'Map': ({'hidePanControl': 'O:Boolean', 'hideZoomControl': 'O:Boolean', 'hideMapTypeControl': 'O:Boolean', 'hideScaleControl': 'O:Boolean', 'hideRotateControl': 'O:Boolean', 'marker': 'O:Boolean', 'centerLat': 'O:enum', 'centerLong': 'O:enum', 'mapSource': 'O:enum', 'mapType': 'O:enum', 'zoom': 'O:Integer', 'width': 'O:String', 'height': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MARKERCLICK': 'E:String'}, ()),
    'Masked Text': ({'monospace': 'O:Boolean', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'mask': 'O:String', 'autoclear': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String', 'eventON_INPUT': 'E:String'}, ()),
    'Modal Alert': ({'colorStyle': 'O:enum', 'buttonLabel': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_SHOW': 'E:String', 'eventON_CLOSE': 'E:String'}, ()),
    'Modal Section': ({'modalWellWidth': 'O:String', 'closeOnClick': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CLOSE': 'E:String', 'eventON_SHOW': 'E:String', 'showModalButtonGroup': 'O:Boolean', 'primaryBtnText': 'O:String', 'secondaryBtnText': 'O:String', 'colorStyle': 'O:enum', 'eventPRIMARY_ON_CLICK': 'E:String', 'eventSECONDARY_ON_CLICK': 'E:String'}, ('ContentBox1',)),
    'Multi Purpose Chart': ({'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'mdsDataService': 'S:enum', 'multiDataSeries': 'LO:enum', 'mds': 'O:Boolean', 'dataMode': 'O:enum', 'defaultChartType': 'O:enum', 'enableMenu': 'O:Boolean', 'maxYAxisTicks': 'O:Integer', 'yAxisTickPrecision': 'O:Integer', 'minYAxisValue': 'O:enum', 'maxYAxisValue': 'O:enum', 'xAxisCulling': 'O:Boolean', 'maxXTickCount': 'O:Integer', 'tooltipStyle': 'O:enum', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'LO:enum', 'showValueLabels': 'O:Boolean', 'showBreadCrumbs': 'O:Boolean', 'pointSize': 'O:enum', 'xyAxisColorStyle': 'O:enum', 'horizontalGridlineStyle': 'O:enum', 'legendPlacement': 'O:enum', 'xLabelRotation': 'O:enum', 'xAxisHeight': 'O:Integer', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Multi Select': ({'tabIndex': 'O:Integer', 'itemLookupMode': 'O:enum', 'itemService': 'S:enum', 'inputData': 'O:ANY', 'itemList': 'LO:ANY', 'staticList': 'LO:enum', 'dataMapping': 'O:enum', 'businessDataMapping': 'O:enum', 'sizeStyle': 'O:enum', 'width': 'O:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_SVCITEMS': 'E:String', 'eventON_SVCERROR': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String'}, ()),
    'Navigation Event': ({'eventData': 'O:ANY', 'eventON_LOAD': 'E:String', 'eventON_TRIGGER': 'E:String', 'eventON_BOUNDARYEVT': 'E:String'}, ()),
    'Note': ({'expression': 'E:String', 'width': 'O:String', 'labelStyle': 'O:enum', 'colorStyle': 'O:enum', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ()),
    'Notification': ({'expression': 'E:String', 'colorStyle': 'O:enum', 'icon': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ()),
    'OpenLayers API': ({'APIKey': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_APILOADED': 'E:String'}, ()),
    'Output Text': ({'expression': 'E:String', 'width': 'O:String', 'textAlignment': 'O:enum', 'colorStyle': 'O:enum', 'sizeStyle': 'O:enum', 'weightStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'eventON_LOAD': 'E:String', 'allowHTML': 'O:Boolean', 'labelWeightNormal': 'O:Boolean'}, ()),
    'Panel': ({'expression': 'E:String', 'icon': 'O:String', 'colorStyle': 'O:enum', 'lightColor': 'O:Boolean', 'colorfulBody': 'O:Boolean', 'width': 'O:String', 'height': 'O:String', 'footerText': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_ICONCLICK': 'E:String'}, ('ContentBox1',)),
    'Panel Footer': ({'eventON_LOAD': 'E:String'}, ('ContentBox1',)),
    'Panel Header': ({'eventON_LOAD': 'E:String'}, ('ContentBox1',)),
    'Password': ({'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String', 'eventON_INPUT': 'E:String'}, ()),
    'Pie Chart SDS': ({'dataMode': 'O:enum', 'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'enableMenu': 'O:Boolean', 'showTooltip': 'O:Boolean', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'LO:enum', 'showBreadCrumbs': 'O:Boolean', 'legendPlacement': 'O:enum', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Places': ({'eventON_LOAD': 'E:String', 'eventON_PLACESREQ': 'E:String', 'eventON_PLACES': 'E:String', 'eventON_PLACESERR': 'E:String'}, ()),
    'Popup Menu': ({'showLabel': 'O:Boolean', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'horizAlign': 'O:enum', 'vertAlign': 'O:enum', 'castShadow': 'O:Boolean', 'width': 'O:String', 'menuSticky': 'O:Boolean', 'menuItems': 'LO:enum', 'eventON_LOAD': 'E:String', 'eventON_ICLICK': 'E:String', 'eventON_SHOW': 'E:String', 'eventON_CLOSE': 'E:String'}, ('ContentBox1',)),
    'Progress Bar': ({'expression': 'E:String', 'maxValue': 'O:enum', 'colorStyle': 'O:enum', 'striped': 'O:Boolean', 'active': 'O:Boolean', 'radius': 'O:String', 'width': 'O:String', 'height': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ()),
    'QR Code': ({'expression': 'E:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'width': 'O:String', 'height': 'O:String', 'backgroundImageURL': 'O:String', 'errorCorrectionLevel': 'O:enum', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String'}, ()),
    'Radio Button': ({'tabIndex': 'O:Integer', 'valueWhenSelected': 'O:String', 'groupName': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_SELECTED': 'E:String'}, ()),
    'Radio Button Group': ({'itemLookupMode': 'O:enum', 'itemService': 'S:enum', 'inputData': 'O:ANY', 'itemList': 'LO:ANY', 'staticList': 'LO:enum', 'dataMapping': 'O:enum', 'width': 'O:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_SVCITEMS': 'E:String', 'eventON_SVCERROR': 'E:String', 'eventON_CHANGE': 'E:String', 'tabIndex': 'O:String'}, ()),
    'Responsive Sensor': ({'boxFactors': 'LO:enum', 'eventON_LOAD': 'E:String', 'eventON_BOUNDARY': 'E:String'}, ('ContentBox1',)),
    'Service Call': ({'expression': 'E:String', 'attachedService': 'S:enum', 'inputData': 'O:ANY', 'autoRun': 'O:Boolean', 'busyIndicator': 'O:enum', 'eventON_LOAD': 'E:String', 'eventON_SVCINVOKE': 'E:String', 'eventON_SVCBEFORERESULT': 'E:String', 'eventON_SVCRESULT': 'E:String', 'eventON_SVCERROR': 'E:String'}, ()),
    'Service Data Table': ({'dataService': 'S:enum', 'queryData': 'O:ANY', 'startEmpty': 'O:Boolean', 'selectionMode': 'O:enum', 'showFooter': 'O:Boolean', 'showTableStats': 'O:Boolean', 'showPager': 'O:Boolean', 'showPageSizer': 'O:Boolean', 'pageSize': 'O:Integer', 'columnSpecs': 'LO:enum', 'tableStyle': 'O:enum', 'colorStyle': 'O:enum', 'highlightSel': 'O:Boolean', 'width': 'O:String', 'height': 'O:String', 'deferLoad': 'O:Boolean', 'loadBatchSize': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_DATALOADED': 'E:String', 'eventON_DATAERROR': 'E:String', 'eventON_NEWCELL': 'E:String', 'eventON_ROWSLOADED': 'E:String', 'eventON_ROWSEL': 'E:String', 'eventON_ALLROWS': 'E:String', 'eventON_SORTING': 'E:String'}, ('ContentBox1',)),
    'Signature': ({'inkColor': 'O:String', 'colorStyle': 'O:enum', 'borderWidth': 'O:String', 'radius': 'O:String', 'shadow': 'O:Boolean', 'width': 'O:String', 'height': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGED': 'E:String'}, ()),
    'Single Select': ({'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'itemLookupMode': 'O:enum', 'itemService': 'S:enum', 'inputData': 'O:ANY', 'itemList': 'LO:ANY', 'staticList': 'LO:enum', 'dataMapping': 'O:enum', 'businessDataMapping': 'O:enum', 'sizeStyle': 'O:enum', 'width': 'O:String', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_SVCITEMS': 'E:String', 'eventON_SVCERROR': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String'}, ()),
    'Slider': ({'expression': 'E:String', 'min': 'O:enum', 'max': 'O:enum', 'step': 'O:enum', 'tabIndex': 'O:Integer', 'vertical': 'O:Boolean', 'colorStyle': 'O:enum', 'height': 'O:String', 'width': 'O:String', 'radius': 'O:String', 'handleWidth': 'O:String', 'handleRadius': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String'}, ()),
    'Spacer': ({'width': 'O:String', 'height': 'O:String', 'animateSizeChgs': 'O:Boolean'}, ()),
    'Stack': ({'defaultPaneIdx': 'O:Integer'}, ('ContentBox1',)),
    'Status Box': ({'expression': 'E:String', 'width': 'O:String', 'colorStyle': 'O:enum', 'statusStyle': 'O:enum', 'floatStatus': 'O:Boolean', 'showStatus': 'O:Boolean', 'showValidationErrors': 'O:Boolean', 'htmlStatus': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_SCLICK': 'E:String'}, ('ContentBox1',)),
    'Step Chart SDS': ({'dataMode': 'O:enum', 'sdsDataService': 'S:enum', 'singleDataSeries': 'O:enum', 'enableMenu': 'O:Boolean', 'maxYAxisTicks': 'O:Integer', 'yAxisTickPrecision': 'O:Integer', 'minYAxisValue': 'O:enum', 'maxYAxisValue': 'O:enum', 'xAxisCulling': 'O:Boolean', 'maxXTickCount': 'O:Integer', 'showTooltip': 'O:Boolean', 'showArea': 'O:Boolean', 'backgroundColorStyle': 'O:enum', 'dataSeriesColorStyle': 'O:enum', 'dataSeriesCustomColorStyle': 'O:enum', 'showValueLabels': 'O:Boolean', 'showBreadCrumbs': 'O:Boolean', 'xyAxisColorStyle': 'O:enum', 'horizontalGridlineStyle': 'O:enum', 'xLabelRotation': 'O:enum', 'xAxisHeight': 'O:Integer', 'radius': 'O:String', 'padding': 'O:String', 'height': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_REFRESH': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_MENUCMD': 'E:String'}, ()),
    'Style': ({'styleSpecs': 'LO:enum'}, ()),
    'Switch': ({'colorStyle': 'O:enum', 'shapeStyle': 'O:enum', 'sizeStyle': 'O:enum', 'labelType': 'O:enum', 'onLabel': 'O:String', 'offLabel': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String'}, ()),
    'Tab Section': ({'defaultPaneIdx': 'O:Integer', 'colorStyle': 'O:enum', 'tabsStyle': 'O:enum', 'sizeStyle': 'O:enum', 'eventON_LOAD': 'E:String', 'eventON_TABCHANGE': 'E:String'}, ('ContentBox1',)),
    'Table': ({'selectionMode': 'O:enum', 'showDeleteButton': 'O:Boolean', 'showFooter': 'O:Boolean', 'showAddButton': 'O:Boolean', 'showTableStats': 'O:Boolean', 'showPager': 'O:Boolean', 'showPageSizer': 'O:Boolean', 'pageSize': 'O:Integer', 'columnSpecs': 'LO:enum', 'tableStyle': 'O:enum', 'colorStyle': 'O:enum', 'highlightSel': 'O:Boolean', 'width': 'O:String', 'height': 'O:String', 'allowWrap': 'O:Boolean', 'showPopups': 'O:Boolean', 'deferLoad': 'O:Boolean', 'loadBatchSize': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_NEWCELL': 'E:String', 'eventON_ROWSLOADED': 'E:String', 'eventON_ROWSEL': 'E:String', 'eventON_ALLROWS': 'E:String', 'eventON_ADDREC': 'E:String', 'eventON_DELREC': 'E:String', 'eventON_SORTING': 'E:String', 'eventON_PAGESIZERCHANGE': 'E:String', 'headerFooterStyle': 'O:enum'}, ('ContentBox1',)),
    'Table Layout': ({'borderSpacing': 'O:String', 'borderCollapse': 'O:enum'}, ('ContentBox1',)),
    'Table Layout Cell': ({}, ('ContentBox1',)),
    'Table Layout Row': ({}, ('ContentBox1',)),
    'Text': ({'expression': 'E:String', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'tabIndex': 'O:Integer', 'labelWidth': 'O:String', 'placeHolder': 'O:String', 'regExp': 'O:String', 'selectAll': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String', 'eventON_INPUT': 'E:String'}, ()),
    'Text Area': ({'width': 'O:String', 'height': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'regExp': 'O:String', 'printOverflow': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String', 'eventON_INPUT': 'E:String'}, ()),
    'Text Editor': ({'width': 'O:String', 'height': 'O:String', 'tabIndex': 'O:Integer', 'colorMap': 'LO:enum', 'colorCols': 'O:Integer', 'colorRows': 'O:Integer', 'showStatus': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String', 'eventON_FOCUS': 'E:String', 'eventON_BLUR': 'E:String'}, ()),
    'Text Reader': ({'width': 'O:String', 'height': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'maxTextLen': 'O:Integer', 'labelWidth': 'O:String', 'readMoreHint': 'O:String', 'readLessHint': 'O:String', 'initiallyExpanded': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'eventON_EXPAND': 'E:String', 'eventON_COLLAPSE': 'E:String'}, ()),
    'Timer': ({'timeout': 'O:Integer', 'repeat': 'O:Boolean', 'stopped': 'O:Boolean', 'eventON_TIMEOUT': 'E:String', 'eventON_BOUNDARYEVT': 'E:String'}, ()),
    'Tooltip': ({'expression': 'E:String', 'showLabel': 'O:Boolean', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'width': 'O:String', 'colorStyle': 'O:enum', 'horizontalPos': 'O:enum', 'verticalPos': 'O:enum', 'showTooltip': 'O:Boolean', 'showOnHover': 'O:Boolean', 'htmlText': 'O:Boolean', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String', 'sizeStyle': 'O:enum'}, ('ContentBox1',)),
    'Type Ahead Text': ({'itemLookupMode': 'O:enum', 'itemService': 'S:enum', 'itemList': 'LO:String', 'width': 'O:String', 'sizeStyle': 'O:enum', 'labelPlacement': 'O:enum', 'labelWidth': 'O:String', 'tabIndex': 'O:Integer', 'placeHolder': 'O:String', 'dropdownItems': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String'}, ()),
    'Variant': ({'autoSelectControl': 'O:Boolean', 'initialControlIndex': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CHANGE': 'E:String'}, ('ContentBox1',)),
    'Vertical Layout': ({'layoutFlow': 'O:enum', 'hAlignment': 'O:enum', 'vAlignment': 'O:enum', 'width': 'O:String', 'height': 'O:String', 'startEmpty': 'O:Boolean', 'sensor': 'O:String', 'behaviors': 'LO:enum', 'deferLoad': 'O:Boolean', 'loadBatchSize': 'O:Integer', 'eventON_LOAD': 'E:String', 'eventON_RESUPD': 'E:String'}, ('ContentBox1',)),
    'Video': ({'width': 'O:String', 'height': 'O:String', 'posterURL': 'O:String', 'sourceType': 'O:enum', 'autoPreload': 'O:Boolean', 'autoPlay': 'O:Boolean', 'tracks': 'LO:enum', 'eventON_LOAD': 'E:String'}, ()),
    'Well': ({'colorStyle': 'O:enum', 'colorDarkness': 'O:enum', 'icon': 'O:String', 'iconSize': 'O:String', 'iconPosition': 'O:enum', 'vAlignment': 'O:enum', 'padding': 'O:String', 'radius': 'O:String', 'width': 'O:String', 'height': 'O:String', 'eventON_LOAD': 'E:String', 'eventON_CLICK': 'E:String'}, ('ContentBox1',)),
}

# ------------------------------------------------------------------------------------------------------ coach layout helpers
def responsive(v): return json.dumps({"isResponsiveData": True, "values": [{"deviceConfigID": "LargeID", "value": v}]})

class Layout:
    """Renders CoachDesignerNG layout XML (ViewRef items of UI Toolkit controls). ns = 'ns18' inside a human service coach (inline XML),
    'ns2' inside a coach view (the whole layout is stored escaped). Ids: uuid5 in the app namespace, so rebuilds are stable."""
    def __init__(self, app, ns, scope):
        self.app = app; self.ns = ns; self.scope = scope; self.n = 0; self.item_ids = []
    def uid(self):
        self.n += 1; return self.app.did('layout', self.scope, self.n)
    def cfg(self, name, value, dynamic=False):
        ns = self.ns
        return (f'<{ns}:configData><{ns}:id>{self.uid()}</{ns}:id><{ns}:optionName>{name}</{ns}:optionName><{ns}:value>{esc(value)}</{ns}:value>'
                + (f'<{ns}:valueType>dynamic</{ns}:valueType>' if dynamic else '') + f'</{ns}:configData>')
    def std(self, label, show=True, helptext=''):
        return [self.cfg('@label', label), self.cfg('@helpText', helptext), self.cfg('@labelVisibility', 'SHOW' if show else 'NONE')]
    def ref(self, item_id, view, cfgs, binding=None, boxes=(), top=False, options=None):
        """One control: item_id (unique in the coach), view = UI Toolkit name or a 64. id, cfgs = config data, binding = data binding,
        boxes = [(content box id, [children])], options = {optionName: value | ('dynamic', expression)} appended as config data."""
        ns = self.ns; view_id = VIEWS.get(view, view)
        assert view_id.startswith('64.'), f'unknown view {view}'
        assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', item_id), f'layout item id must be an identifier: {item_id}'
        self.item_ids.append(item_id)
        options = dict(options or {})
        if isinstance(options.get('options'), dict): options.update(options.pop('options'))   # L.output(..., options={...}) meant extra options
        if view in VIEW_OPTIONS:   # OOB control: only declared options (and the @ built-ins) - anything else is a 500 at playback
            declared, boxes_declared = VIEW_OPTIONS[view]
            for k in options:
                assert k.startswith('@') or k in declared, (f"{item_id}: '{view}' has no config option '{k}' (declared: {', '.join(sorted(declared))}); "
                                                            "the coach generator answers 500 for an unknown option")
            for box_id, _ in boxes:
                assert box_id in boxes_declared, f"{item_id}: '{view}' has no content box '{box_id}' (declared: {', '.join(boxes_declared) or 'none'})"
        for k, v in options.items():   # event expressions run in the browser: there is no tw object (ReferenceError: tw is not defined)
            if k.startswith('event') and isinstance(v, str) and re.search(r'\btw\.(local|env|system|object)\b', v):
                raise AssertionError(f"{item_id}: the {k} expression uses tw.* - coach event expressions have no tw object (ReferenceError at "
                                     "click time, on every version). Read values with control getters (${Ctrl}.getText(), getSelectedRecords()) "
                                     "and pass a service input with ${SvcCall}.execute({field: value, ...})")
        for k, v in (options or {}).items():
            cfgs = cfgs + [self.cfg(k, v[1], True) if isinstance(v, tuple) else self.cfg(k, v if isinstance(v, str) else json.dumps(v))]
        if top: head = f'<{ns}:layoutItem xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="{ns}:ViewRef" version="8550">'; tail = f'</{ns}:layoutItem>'
        else: head = f'<{ns}:contributions xsi:type="{ns}:ViewRef" version="8550">'; tail = f'</{ns}:contributions>'
        body = f'<{ns}:id>{self.uid()}</{ns}:id><{ns}:layoutItemId>{item_id}</{ns}:layoutItemId>' + ''.join(cfgs) + f'<{ns}:viewUUID>{view_id}</{ns}:viewUUID>'
        if binding: body += f'<{ns}:binding>{esc(binding)}</{ns}:binding>'
        for box_id, children in boxes:
            body += f'<{ns}:contentBoxContrib><{ns}:id>{self.uid()}</{ns}:id><{ns}:contentBoxId>{box_id}</{ns}:contentBoxId>' + ''.join(children) + f'</{ns}:contentBoxContrib>'
        return head + body + tail
    # ---- controls (label = the visible label; show=False hides it)
    def output(self, item_id, label, binding=None, html=False, show=False, **options):
        o = {'allowHTML': responsive(True)} if html else {}; o.update(options)
        return self.ref(item_id, 'Output Text', self.std(label, show), binding=binding, options=o)
    def text(self, item_id, label, binding=None, width='320px', **options):
        return self.ref(item_id, 'Text', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=options)
    def text_area(self, item_id, label, binding=None, height='300px', **options):
        return self.ref(item_id, 'Text Area', self.std(label) + [self.cfg('@width', responsive('100%')), self.cfg('height', responsive(height))], binding=binding, options=options)
    def integer(self, item_id, label, binding=None, **options):
        return self.ref(item_id, 'Integer', self.std(label), binding=binding, options=options)
    def checkbox(self, item_id, label, binding=None, **options):
        return self.ref(item_id, 'Checkbox', self.std(label), binding=binding, options=options)
    def select(self, item_id, label, binding, items, width='320px', **options):
        """Single Select with a static list: items = [(bound value, shown text)] (the control binds `name`, shows `value`)."""
        o = {'itemLookupMode': 'L', 'staticList': json.dumps([{'name': v, 'value': t} for v, t in items]), 'labelPlacement': 'T'}; o.update(options)
        return self.ref(item_id, 'Single Select', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=o)
    def checkbox_group(self, item_id, label, binding, items, **options):
        """Checkbox Group with a static list (name == value); binding = a list variable (`tw.local.x.states[]`)."""
        o = {'itemLookupMode': 'L', 'staticList': json.dumps([{'name': x, 'value': x} for x in items]), 'labelPlacement': 'T'}; o.update(options)
        return self.ref(item_id, 'Checkbox Group', self.std(label), binding=binding, options=o)
    def date(self, item_id, label, binding=None, **options):
        return self.ref(item_id, 'Date Time Picker', self.std(label), binding=binding, options=options)
    def button(self, item_id, label, on_click=None, style='D', **options):
        """style: P primary, D default, S success, I info, W warning, G danger. on_click = event expression (no backslashes!)."""
        o = {'colorStyle': style}; o.update(options)
        if on_click: o['eventON_CLICK'] = on_click     # None = the button only fires its boundary event (an exit of a task coach)
        return self.ref(item_id, 'Button', self.std(label), options=o)
    def link(self, item_id, label, url_expr, **options):
        o = {'linkURL': ('dynamic', url_expr), 'sameWindow': 'false'}; o.update(options)
        return self.ref(item_id, 'Link', self.std(label), options=o)
    def hlayout(self, item_id, children, wrap=True, label=''):
        return self.ref(item_id, 'Horizontal Layout', self.std(label or item_id, False) + ([self.cfg('layoutFlow', 'W')] if wrap else []), boxes=[('ContentBox1', children)])
    def vlayout(self, item_id, children, label='', top=False):
        return self.ref(item_id, 'Vertical Layout', self.std(label or item_id, False), boxes=[('ContentBox1', children)], top=top)
    def panel(self, item_id, title, children, style='D', **options):
        o = {'colorStyle': style}; o.update(options)
        return self.ref(item_id, 'Panel', self.std(title), boxes=[('ContentBox1', children)], options=o)
    def tabs(self, item_id, label, panes, style='P', **options):
        """Tab Section: every child of ContentBox1 is a tab, its @label is the tab title."""
        o = {'colorStyle': style}; o.update(options)
        return self.ref(item_id, 'Tab Section', self.std(label), boxes=[('ContentBox1', panes)], options=o)
    def table(self, item_id, title, binding, cols, selection='S', page=15, on_rowsel=None, **options):
        """UI Toolkit Table bound to a list (`tw.local.result.rows`): cols = [(field, header)] rendered as Output Text children bound to
        currentItem.<field>; selection S single / M multiple / N none; on_rowsel = event expression (read the selection with getSelectedRecords())."""
        children = [self.ref(f'{item_id}_{re.sub("[^A-Za-z0-9]", "", f)}', 'Output Text', self.std(label), binding=f'{binding}.currentItem.{f}') for f, label in cols]
        specs = json.dumps([{"dataElementName": f, "renderAs": "V", "visibility": "V", "sortable": True, "options": "", "css": "", "width": "", "label": label} for f, label in cols])
        o = {'columnSpecs': specs, 'selectionMode': selection, 'showFooter': responsive(True), 'showPager': responsive(True), 'showPageSizer': responsive(False),
             'pageSize': responsive(page), 'showTableStats': responsive(True), 'tableStyle': 'S', '@width': responsive('100%')}
        if on_rowsel: o['eventON_ROWSEL'] = on_rowsel
        o.update(options)
        return self.ref(item_id, 'Table', self.std(title), binding=f'{binding}[]', boxes=[('ContentBox1', children)], options=o)
    def service(self, item_id, flow, input_binding=None, result_binding=None, on_result=None, on_error=None, status='StatusLine'):
        """Service Call control attached to an Ajax service flow of this app (input parameter `data`, output `results`).
        `${item_id}.execute()` runs it with the bound input, `${item_id}.execute(obj)` with an explicit object; the result lands in
        result_binding and the On result / On error expressions run (`result`, `error` are available there)."""
        fid = self.app.flow_id(flow)
        on_result = on_result if on_result is not None else f'${{{status}}}.setText(result && result.message ? result.message : "Done");'
        on_error = on_error if on_error is not None else f'${{{status}}}.setText("Error: " + (error && error.errorText ? error.errorText : error));'
        cfgs = self.std(item_id, False) + [self.cfg('attachedService', fid), self.cfg('autoRun', 'false'), self.cfg('busyIndicator', 'S'),
                                          self.cfg('eventON_SVCRESULT', on_result), self.cfg('eventON_SVCERROR', on_error)]
        if input_binding: cfgs.append(self.cfg('inputData', input_binding, True))
        return self.ref(item_id, 'Service Call', cfgs, binding=result_binding)
    def modal(self, item_id, title, children, primary='OK', primary_expr=None, secondary='Close', width='800px', style=None):
        """Modal Section, hidden until `${item_id}.show()`; the secondary button closes it, the primary runs primary_expr (then closes)."""
        primary_expr = primary_expr or f'${{{item_id}}}.setVisible(false);'
        o = {'@visibility': responsive('HIDDEN'), 'modalWellWidth': width, 'showModalButtonGroup': 'true', 'primaryBtnText': primary, 'secondaryBtnText': secondary,
             'eventPRIMARY_ON_CLICK': primary_expr, 'eventSECONDARY_ON_CLICK': f'${{{item_id}}}.setVisible(false);'}
        if style: o['colorStyle'] = style
        return self.ref(item_id, 'Modal Section', self.std(title), boxes=[('ContentBox1', children)], options=o)
    def hidden(self, item_id):
        """Hidden Output Text - a scratch value carrier between a table selection and a service call (`${X}.setText(v)` / `${X}.getText()`)."""
        return self.ref(item_id, 'Output Text', self.std(item_id, False) + [self.cfg('@visibility', responsive('HIDDEN'))])
    def custom(self, item_id, view, label='', binding=None, options=None, children=None):
        """A coach view of this app (name given to app.coach_view) or any 64. id; options = {optionName: 'literal' | ('dynamic', 'tw.local.x')}."""
        view_id = self.app.view_ids.get(view, view)
        return self.ref(item_id, view_id, self.std(label or item_id, bool(label)), binding=binding, options=options, boxes=[('ContentBox1', children)] if children else ())
    def status_line(self, item_id='StatusLine'): return self.output(item_id, 'Status')
    def message_modal(self, item_id='Msg'):
        return self.modal(item_id, 'Message', [self.output(item_id + 'Text', item_id + 'Text')], primary='OK', width='700px')
    # ---- more UI Toolkit controls (added with the UI Controls Kit; each proven in playback - see the controls catalogue in the knowledge base)
    # inputs
    def decimal(self, item_id, label, binding=None, places=2, currency=None, width='240px', **options):
        """Decimal (binding Decimal): decimalPlaces, currency = ISO code such as 'EUR' (None = plain number), prefix / postfix, placeHolder."""
        o = {'decimalPlaces': str(places)}
        if currency: o['currency'] = currency
        o.update(options)
        return self.ref(item_id, 'Decimal', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=o)
    def radio_group(self, item_id, label, binding, items, **options):
        """Radio Button Group with a static list (binding ANY -> a String variable holds the `name`): items = [(bound value, shown text)]."""
        o = {'itemLookupMode': 'L', 'staticList': json.dumps([{'name': v, 'value': t} for v, t in items]), 'labelPlacement': 'T'}; o.update(options)
        return self.ref(item_id, 'Radio Button Group', self.std(label), binding=binding, options=o)
    def radio(self, item_id, label, binding, value, group, **options):
        """One Radio Button (binding ANY shared by the buttons of a groupName): selecting it writes valueWhenSelected into the binding."""
        o = {'valueWhenSelected': value, 'groupName': group}; o.update(options)
        return self.ref(item_id, 'Radio Button', self.std(label), binding=binding, options=o)
    def multi_select(self, item_id, label, binding, items, width='320px', **options):
        """Multi Select with a static list (binding = a list variable `tw.local.x.tags[]`, receives the `name` values): items = [(value, text)]."""
        o = {'itemLookupMode': 'L', 'staticList': json.dumps([{'name': v, 'value': t} for v, t in items]), 'labelPlacement': 'T'}; o.update(options)
        return self.ref(item_id, 'Multi Select', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=o)
    def select_service(self, item_id, label, binding, flow, input_binding=None, width='320px', view='Single Select', **options):
        """Single Select (or view='Multi Select' / 'Radio Button Group' / 'Checkbox Group') whose items come from an Ajax flow of this app:
        input `data` (input_binding), output `results` = NameValuePair[] (name = bound value, value = shown text)."""
        o = {'itemLookupMode': 'S', 'itemService': self.app.flow_id(flow), 'labelPlacement': 'T'}
        if input_binding: o['inputData'] = ('dynamic', input_binding)
        o.update(options)
        return self.ref(item_id, view, self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=o)
    def date_picker(self, item_id, label, binding=None, fmt=None, **options):
        """Date Picker (binding Date, date only, text box + calendar): fmt = display format such as 'yyyy-mm-dd' (lower-case tokens),
        enableTodayButton / enableClearButton 'true', startView 0 month / 1 year / 2 decade."""
        o = {}
        if fmt: o['format'] = fmt
        o.update(options)
        return self.ref(item_id, 'Date Picker', self.std(label), binding=binding, options=o)
    def datetime(self, item_id, label, binding=None, time=True, fmt=None, **options):
        """Date Time Picker (binding Date): time=True adds the time picker (includeTimePicker); fmt = Java SimpleDateFormat pattern
        ('yyyy-MM-dd HH:mm'); date() is the same control without the time part."""
        o = {'includeTimePicker': 'true' if time else 'false'}
        if fmt: o['format'] = fmt
        o.update(options)
        return self.ref(item_id, 'Date Time Picker', self.std(label), binding=binding, options=o)
    def masked_text(self, item_id, label, binding=None, mask='(###) ###-####', width='240px', **options):
        """Masked Text (binding String): mask = # digit, a letter, * either, other characters are literals kept in the bound value."""
        o = {'mask': mask}; o.update(options)
        return self.ref(item_id, 'Masked Text', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=o)
    def password(self, item_id, label, binding=None, width='240px', **options):
        """Password (binding String, masked input)."""
        return self.ref(item_id, 'Password', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=options)
    def type_ahead(self, item_id, label, binding=None, items=(), width='240px', **options):
        """Type Ahead Text (binding String): items = static suggestions (itemLookupMode L, itemList = JSON list of strings), dropdownItems."""
        o = {'itemLookupMode': 'L', 'itemList': json.dumps(list(items))}; o.update(options)
        return self.ref(item_id, 'Type Ahead Text', self.std(label) + [self.cfg('@width', responsive(width))], binding=binding, options=o)
    def text_editor(self, item_id, label, binding=None, height='160px', **options):
        """Text Editor (binding String = the HTML of the rich text)."""
        return self.ref(item_id, 'Text Editor', self.std(label) + [self.cfg('@width', responsive('100%')), self.cfg('height', responsive(height))], binding=binding, options=options)
    def text_reader(self, item_id, label, binding=None, max_len=128, **options):
        """Text Reader (binding String): read-only text cut after max_len characters with a read more / read less link (readMoreHint / readLessHint)."""
        o = {'maxTextLen': str(max_len)}; o.update(options)
        return self.ref(item_id, 'Text Reader', self.std(label), binding=binding, options=o)
    def switch(self, item_id, label, binding=None, on='On', off='Off', style='P', **options):
        """Switch (binding Boolean): onLabel / offLabel (text, or icon names with labelType I), colorStyle D/P/I/S/W/G, shapeStyle D/S/M."""
        o = {'onLabel': on, 'offLabel': off, 'colorStyle': style}; o.update(options)
        return self.ref(item_id, 'Switch', self.std(label), binding=binding, options=o)
    def slider(self, item_id, label, binding=None, min=0, max=100, step=1, style='P', width='320px', **options):
        """Slider (binding Decimal): min / max / step, colorStyle D/P/I/S/W/E; getValue() / setValue()."""
        o = {'min': str(min), 'max': str(max), 'step': str(step), 'colorStyle': style, 'width': responsive(width)}; o.update(options)
        return self.ref(item_id, 'Slider', self.std(label), binding=binding, options=o)
    def signature(self, item_id, label, binding=None, width='320px', height='120px', **options):
        """Signature (binding String = PNG data URL of the drawing): width / height in px; clear(); isEmpty() is false until clear() ran once."""
        o = {'width': responsive(width), 'height': responsive(height)}; o.update(options)
        return self.ref(item_id, 'Signature', self.std(label), binding=binding, options=o)
    def qr_code(self, item_id, label, binding=None, size='140px', **options):
        """QR Code (binding String = the encoded text): width / height, errorCorrectionLevel L/M/Q/H."""
        o = {'width': responsive(size), 'height': responsive(size)}; o.update(options)
        return self.ref(item_id, 'QR Code', self.std(label), binding=binding, options=o)
    # display
    def badge(self, item_id, text, style='P', shape='B', **options):
        """Badge (no binding): text set on load, colorStyle D/P/I/S/W/E, shapeStyle B badge / L label / T tag; setText()."""
        o = {'colorStyle': style, 'shapeStyle': shape, 'eventON_LOAD': f'me.setText({json.dumps(text)});'}; o.update(options)
        return self.ref(item_id, 'Badge', self.std(item_id, False), options=o)
    def icon(self, item_id, icon, style='P', size='24px', on_click=None, **options):
        """Icon (binding Boolean isClicked, optional): Font Awesome name, colorStyle D/P/I/S/W/G/T, iconSize; on_click = event expression."""
        o = {'icon': icon, 'colorStyle': style, 'iconSize': responsive(size)}
        if on_click: o['eventON_CLICK'] = on_click
        o.update(options)
        return self.ref(item_id, 'Icon', self.std(item_id, False), options=o)
    def image(self, item_id, url, app=None, external=False, width='120px', height=None, **options):
        """Image (unbound): url = the name of a web file of this app (app=None) or of another app / toolkit (its acronym), served as a
        managed asset (defaultURLType Web), or an absolute URL with external=True; width / height, radius."""
        o = {'defaultURL': responsive(url), 'defaultURLType': 'External' if external else 'Web', 'width': responsive(width)}
        if not external: o['defaultAppAcronym'] = responsive(app or self.app.acronym)
        if height: o['height'] = responsive(height)
        o.update(options)
        return self.ref(item_id, 'Image', self.std(item_id, False), options=o)
    def line(self, item_id):
        """Line: a horizontal rule (no options, no binding)."""
        return self.ref(item_id, 'Line', self.std(item_id, False))
    def note(self, item_id, title, binding=None, text=None, style='I', heading='H4', **options):
        """Note (binding String = the text, or text= set on load): label = title, colorStyle D/P/S/I/W/G, labelStyle H1..H4."""
        o = {'colorStyle': style, 'labelStyle': heading}
        if text: o['eventON_LOAD'] = f'me.setText({json.dumps(text)});'
        o.update(options)
        return self.ref(item_id, 'Note', self.std(title), binding=binding, options=o)
    def notification(self, item_id, text, style='W', icon='bell', **options):
        """Notification (no binding): text set on load, colorStyle D/P/I/S/W/E, icon = Font Awesome name; setText()."""
        o = {'colorStyle': style, 'icon': icon, 'eventON_LOAD': f'me.setText({json.dumps(text)});'}; o.update(options)
        return self.ref(item_id, 'Notification', self.std(item_id, False), options=o)
    def well(self, item_id, children, style='D', icon=None, **options):
        """Well (ContentBox1): colorStyle D/P/I/S/W/G, colorDarkness N/D/R, icon (Font Awesome) + iconPosition TR/TL/BR/BL, padding."""
        o = {'colorStyle': style}
        if icon: o['icon'] = responsive(icon)
        o.update(options)
        return self.ref(item_id, 'Well', self.std(item_id, False), boxes=[('ContentBox1', children)], options=o)
    def tooltip(self, item_id, text, children, style='D', **options):
        """Tooltip around one control (ContentBox1): text shown on hover (showOnHover), colorStyle, horizontalPos L/C/R, verticalPos T/B."""
        o = {'colorStyle': style, 'showOnHover': 'true', 'eventON_LOAD': f'me.setText({json.dumps(text)});'}; o.update(options)
        return self.ref(item_id, 'Tooltip', self.std(item_id, False), boxes=[('ContentBox1', children)], options=o)
    def progress(self, item_id, label, binding=None, max=100, style='S', **options):
        """Progress Bar (binding Decimal): maxValue = the 100 % value, colorStyle D/P/I/S/W/G, striped / active; setProgress() / getProgress()."""
        o = {'maxValue': str(max), 'colorStyle': style}; o.update(options)
        return self.ref(item_id, 'Progress Bar', self.std(label), binding=binding, options=o)
    def spacer(self, item_id, width='100%', height='12px'):
        """Spacer: an empty box of width x height."""
        return self.ref(item_id, 'Spacer', self.std(item_id, False), options={'width': responsive(width), 'height': responsive(height)})
    def status_box(self, item_id, label='', children=(), style='I', status_style='D', **options):
        """Status Box (ContentBox1 optional): the strip element is created when the status becomes visible while a text is set, so show a
        status with `${id}.setStatusText(t); ${id}.setStatusVisible(false); ${id}.setStatusVisible(true);` (setStatusText alone shows
        nothing); colorStyle D/P/S/I/W/E, statusStyle N plain paragraph / D strip / K dark / S simple."""
        o = {'colorStyle': style, 'statusStyle': status_style, 'showStatus': responsive(True)}; o.update(options)
        return self.ref(item_id, 'Status Box', self.std(label, bool(label)), boxes=[('ContentBox1', list(children))] if children else (), options=o)
    # structure
    def collapsible(self, item_id, title, children, collapsed=False, group=None, style='D', on_expand=None, on_collapse=None, **options):
        """Collapsible Panel (ContentBox1): initiallyCollapsed, panelGroup (one open panel per group), colorStyle D/P/S/I/W/G; expand() / collapse() / isExpanded()."""
        o = {'initiallyCollapsed': 'true' if collapsed else 'false', 'colorStyle': style}
        if group: o['panelGroup'] = group
        if on_expand: o['eventON_EXPAND'] = on_expand
        if on_collapse: o['eventON_COLLAPSE'] = on_collapse
        o.update(options)
        return self.ref(item_id, 'Collapsible Panel', self.std(title), boxes=[('ContentBox1', children)], options=o)
    def hsplit(self, item_id, panes, height='240px', **options):
        """Horizontal Split (ContentBox1, one pane per child): panes = [(size such as '30%', [children])]; paneSpecs = size / handleLocation
        N/M/S/E per pane; the control needs an explicit height. collapsePane(i) / expandPane(i) / isPaneCollapsed(i)."""
        specs = [{'size': size, 'collapsedSize': '', 'splitterThickness': '', 'handleLocation': 'M'} for size, _ in panes]
        children = [self.vlayout(f'{item_id}Pane{i}', c) for i, (_, c) in enumerate(panes)]
        o = {'height': height, 'paneSpecs': json.dumps(specs)}; o.update(options)
        return self.ref(item_id, 'Horizontal Split', self.std(item_id, False), boxes=[('ContentBox1', children)], options=o)
    def input_group(self, item_id, label, children, button='search', kind='I', style='P', location='R', on_click=None, **options):
        """Input Group (ContentBox1 = one input control) with an attached button: buttonKind I icon / T text / M menu, buttonInfo = icon
        name or text, buttonLocation L/R, buttonColorStyle; on_click = On button click expression."""
        o = {'buttonKind': kind, 'buttonInfo': button, 'buttonColorStyle': style, 'buttonLocation': location, 'labelPlacement': 'T'}
        if on_click: o['eventON_CLICK'] = on_click
        o.update(options)
        return self.ref(item_id, 'Input Group', self.std(label), boxes=[('ContentBox1', children)], options=o)
    def caption(self, item_id, label, child, placement='L', width='60%', **options):
        """Caption Box (ContentBox1 = exactly one child): label placed T/L/B/R of the child, labelWidth, labelColorStyle."""
        o = {'labelPlacement': placement, 'width': responsive(width)}; o.update(options)
        return self.ref(item_id, 'Caption Box', self.std(label), boxes=[('ContentBox1', [child])], options=o)
    def stack(self, item_id, panes, default=0, **options):
        """Stack (ContentBox1, one pane per child, one visible at a time): defaultPaneIdx; setCurrentPane(i) / getCurrentPane(); binding Integer = pane index."""
        o = {'defaultPaneIdx': str(default)}; o.update(options)   # getCurrentPane() answers null until setCurrentPane() ran once (unbound stack)
        return self.ref(item_id, 'Stack', self.std(item_id, False), boxes=[('ContentBox1', panes)], options=o)
    def table_layout(self, item_id, rows, collapse=True, **options):
        """Table Layout > Table Layout Row > Table Layout Cell grid: rows = [[cell children, ...], ...] (each cell = a list of controls); borderCollapse C/S."""
        row_items = []
        for r, cells in enumerate(rows):
            cell_items = [self.ref(f'{item_id}R{r}C{c}', 'Table Layout Cell', self.std(f'{item_id}R{r}C{c}', False), boxes=[('ContentBox1', children)]) for c, children in enumerate(cells)]
            row_items.append(self.ref(f'{item_id}R{r}', 'Table Layout Row', self.std(f'{item_id}R{r}', False), boxes=[('ContentBox1', cell_items)]))
        o = {'borderCollapse': 'C' if collapse else 'S'}; o.update(options)
        return self.ref(item_id, 'Table Layout', self.std(item_id, False), boxes=[('ContentBox1', row_items)], options=o)
    def sensor(self, item_id, children, factors=(('narrow', 600), ('wide', 99999)), on_boundary=None, **options):
        """Responsive Sensor (ContentBox1): boxFactors = [(name, widthUpTo px)]; a layout inside declares `behaviors`
        ('[{"boxFactorName": "narrow", "childLayout": "V"}]') per box factor; getActiveBoxFactor(), on_boundary = On responsive boundary."""
        o = {'boxFactors': json.dumps([{'name': n, 'widthUpTo': w} for n, w in factors])}
        if on_boundary: o['eventON_BOUNDARY'] = on_boundary
        o.update(options)
        return self.ref(item_id, 'Responsive Sensor', self.std(item_id, False), boxes=[('ContentBox1', children)], options=o)
    def variant(self, item_id, label, binding, children, auto=True, **options):
        """Variant (binding ANY, ContentBox1 = candidate controls): shows the child matching the type of the bound value (autoSelectControl) or initialControlIndex; getValue() / setValue()."""
        o = {'autoSelectControl': 'true' if auto else 'false'}; o.update(options)
        return self.ref(item_id, 'Variant', self.std(label), binding=binding, boxes=[('ContentBox1', children)], options=o)
    def popup_menu(self, item_id, children, items, on_item=None, **options):
        """Popup Menu around the control in ContentBox1: nothing opens it by itself - the inner control's click calls
        `${id}.setMenuVisible(!${id}.isMenuVisible())`; items = [(command, text[, icon])] or ('-',) for a separator (menuItems);
        on_item = On item click expression, `command` = the clicked item's command."""
        specs = [({'itemType': 'S'} if it[0] == '-' else {'command': it[0], 'itemType': 'L', 'itemText': it[1], 'icon': it[2] if len(it) > 2 else ''}) for it in items]
        o = {'menuItems': json.dumps(specs), 'castShadow': 'true'}
        if on_item: o['eventON_ICLICK'] = on_item
        o.update(options)
        return self.ref(item_id, 'Popup Menu', self.std(item_id, False), boxes=[('ContentBox1', children)], options=o)
    def deferred(self, item_id, children, auto=False, delay=0, on_load=None, **options):
        """Deferred Section (ContentBox1 rendered later): autoLoad + autoLoadDelay ms, or `${id}.lazyLoad(0)` from an event; on_load = On lazy-loaded expression; isLoaded()."""
        o = {'autoLoad': 'true' if auto else 'false', 'autoLoadDelay': str(delay)}
        if on_load: o['eventON_SECLOAD'] = on_load
        o.update(options)
        return self.ref(item_id, 'Deferred Section', self.std(item_id, False), boxes=[('ContentBox1', children)], options=o)
    def panel_header(self, item_id, children):
        """Panel Header (ContentBox1): the title strip of a Panel when placed as its first child."""
        return self.ref(item_id, 'Panel Header', self.std(item_id, False), boxes=[('ContentBox1', children)])
    def panel_footer(self, item_id, children):
        """Panel Footer (ContentBox1): the footer strip of a Panel when placed as its last child."""
        return self.ref(item_id, 'Panel Footer', self.std(item_id, False), boxes=[('ContentBox1', children)])
    # navigation, events, data
    def breadcrumbs(self, item_id, label, binding, on_click=None, **options):
        """Breadcrumbs (binding NameValuePair[]: name = text, value = data): on_click = On item click expression with `label` and
        `item` = {label, level, data}; returning false keeps the trail (it is trimmed to the clicked item otherwise); appendItem() / trim()."""
        o = {}
        if on_click: o['eventON_ITEM_CLICK'] = on_click
        o.update(options)
        return self.ref(item_id, 'Breadcrumbs', self.std(label, bool(label)), binding=binding if binding.endswith('[]') else binding + '[]', options=o)
    def alerts(self, item_id, style='I', fade=0, **options):
        """Alerts (no binding): the area where `${id}.appendAlert(title, text, style P/I/S/W/G, timeoutMs)` shows dismissable alerts;
        alertColorStyle = default style, autoFadeDelay ms (0 = stay), animate; clear()."""
        o = {'alertColorStyle': style, 'autoFadeDelay': str(fade), 'animate': 'true'}; o.update(options)
        return self.ref(item_id, 'Alerts', self.std(item_id, False), options=o)
    def modal_alert(self, item_id, title, style='I', button='OK', on_close=None, **options):
        """Modal Alert: `${id}.setText(msg); ${id}.show();` opens a one-button dialog titled with the label; colorStyle P/I/S/W/G, buttonLabel, on_close = On close."""
        o = {'colorStyle': style, 'buttonLabel': button}
        if on_close: o['eventON_CLOSE'] = on_close
        o.update(options)
        return self.ref(item_id, 'Modal Alert', self.std(title), options=o)
    def exit_safeguard(self, item_id, challenge=False, message='You have unsaved changes.', **options):
        """Exit Safeguard: the browser's leave-page challenge (challengeByDefault, message); setExitChallenged(bool) / isExitChallenged()."""
        o = {'challengeByDefault': 'true' if challenge else 'false', 'message': message}; o.update(options)
        return self.ref(item_id, 'Exit Safeguard', self.std(item_id, False), options=o)
    def event_subscription(self, item_id, event_name, on_event, binding=None, **options):
        """Event Subscription: runs on_event (synchronously) when `bpmext.ui.publishEvent(event_name, payload)` is called anywhere in the
        page; publish a string (JSON text) - an object payload comes back wrapped as a coach object; the payload lands in the binding
        (a String variable) and in getEventData()."""
        o = {'eventName': event_name, 'eventON_EVENT': on_event}; o.update(options)
        return self.ref(item_id, 'Event Subscription', self.std(item_id, False), binding=binding, options=o)
    def timer(self, item_id, ms=1000, repeat=False, stopped=True, on_timeout=None, **options):
        """Timer: timeout ms, repeat, stopped (start() later); on_timeout = On timeout expression; getTicks() / stop() / isRunning()."""
        o = {'timeout': str(ms), 'repeat': 'true' if repeat else 'false', 'stopped': 'true' if stopped else 'false'}
        if on_timeout: o['eventON_TIMEOUT'] = on_timeout
        o.update(options)
        return self.ref(item_id, 'Timer', self.std(item_id, False), options=o)
    def configuration(self, item_id='Config', parameters=None, debugging=False, **options):
        """Configuration (one per coach): parameters = {name: value} read with `${Config}.getParameter(name)`; debugging switch, locale."""
        o = {'debugging': 'true' if debugging else 'false', 'parameters': json.dumps([{'name': k, 'value': v} for k, v in (parameters or {}).items()])}; o.update(options)
        return self.ref(item_id, 'Configuration', self.std(item_id, False), options=o)
    def data(self, item_id, binding=None, **options):
        """Data (binding ANY): an invisible value holder, getValue() / setValue(); its On change fires when the bound data changes."""
        return self.ref(item_id, 'Data', self.std(item_id, False), binding=binding, options=options)
    def device_sensor(self, item_id='Device'):
        """Device Sensor (binding DeviceInfo optional): getDeviceInfo() = {os, browserName, browserMajorVersion, screenWidth, clientWidth, language, isIPad, ...}."""
        return self.ref(item_id, 'Device Sensor', self.std(item_id, False))
    def geo_location(self, item_id, mode='S', on_info=None, on_error=None, **options):
        """Geo Location (binding GeoLocation optional): monitoringMode L once on load / C continuous / S stopped (requestUpdate() later);
        on_info receives `location`, on_error receives `error` (the browser asks the user for permission)."""
        o = {'monitoringMode': mode}
        if on_info: o['eventON_LOCINFO'] = on_info
        if on_error: o['eventON_LOCINFOERR'] = on_error
        o.update(options)
        return self.ref(item_id, 'Geo Location', self.std(item_id, False), options=o)
    def data_export(self, item_id, label, binding=None, table=None, file_type='csv', file_name='export', headers=None, style='D', **options):
        """Data Export button: downloads the bound list (binding `tw.local.rows[]`, one column per field) or the Table named in `table`
        (tableName = a sibling control id) as csv / xlsx (fileType); defName = file name, colHeaders = header texts."""
        o = {'fileType': file_type, 'defName': file_name, 'colNames': 'true', 'colorStyle': style}
        if table: o['tableName'] = table
        if headers: o['colHeaders'] = json.dumps(list(headers))
        o.update(options)
        return self.ref(item_id, 'Data Export', self.std(label), binding=binding, options=o)
    # charts and service-fed tables
    CHARTS = {'bar': 'Bar Chart SDS', 'line': 'Line Chart SDS', 'pie': 'Pie Chart SDS', 'donut': 'Donut Chart SDS', 'area': 'Area Chart SDS', 'step': 'Step Chart SDS', 'multi': 'Multi Purpose Chart'}
    def chart(self, item_id, kind, series=None, flow=None, height=260, style=None, chart_type=None, **options):
        """SDS chart (kind bar / line / pie / donut / area / step) or kind 'multi' = Multi Purpose Chart. Data = a UI Toolkit DataSeries
        {seriesName, dataPoints[{label, value}]}: from a variable (series = 'tw.local.series', dataMode B; for multi a DataSeries[] variable)
        or from an Ajax flow of this app (flow = its name, dataMode S: inputs `input` String + `drillDownStack` NameValuePair[], output
        `dataSeries` DataSeries; multi: output `multiDataSeries` DataSeries[]). height px, dataSeriesColorStyle P/I/S/W/G/L (pie / donut /
        multi accept L default palette), chart_type for multi = B bar / L line / A area / S spline / R area spline / T step / E area step / P pie / D donut.
        getDataSeries() answers {name, items[{label, value}]}; refresh() re-runs the flow, redrawChart() re-sizes a chart drawn in a hidden tab."""
        view = self.CHARTS[kind]
        o = {'height': responsive(height), 'showTooltip': 'true'} if kind not in ('pie', 'donut') else {'height': responsive(height), 'showTooltip': 'true', 'legendPlacement': 'B'}
        if kind == 'multi': o = {'height': responsive(height), 'tooltipStyle': 'G', 'legendPlacement': 'B', 'defaultChartType': chart_type or 'B'}
        if style: o['dataSeriesColorStyle'] = style
        if series:
            o['dataMode'] = 'B'
            if kind == 'multi': o['mds'] = 'true'; o['multiDataSeries'] = ('dynamic', series)
            else: o['singleDataSeries'] = ('dynamic', series)
        elif flow:
            o['dataMode'] = 'S'
            if kind == 'multi': o['mds'] = 'true'; o['mdsDataService'] = self.app.flow_id(flow)
            else: o['sdsDataService'] = self.app.flow_id(flow)
        o.update(options)
        return self.ref(item_id, view, self.std(item_id, False), options=o)
    def service_table(self, item_id, title, flow, binding, cols, input_binding=None, selection='S', page=10, height=None, **options):
        """Service Data Table: rows fetched from an Ajax flow of this app (input `data` = queryData, output `results` = a list of business
        objects) into the bound list variable (`tw.local.svcRows`); the columns are Output Text children bound to currentItem.<field> like
        the Table (the control counts its columns from the children), cols = [(field, header)] also become columnSpecs; refresh(true) reloads
        with the current query data; give it a height when the sticky header overlaps the first row."""
        children = [self.ref(f'{item_id}_{re.sub("[^A-Za-z0-9]", "", f)}', 'Output Text', self.std(label), binding=f'{binding}.currentItem.{f}') for f, label in cols]
        specs = json.dumps([{"dataElementName": f, "renderAs": "H", "visibility": "V", "sortable": True, "options": "", "css": "", "width": "", "label": label} for f, label in cols])
        o = {'dataService': self.app.flow_id(flow), 'columnSpecs': specs, 'selectionMode': selection, 'showFooter': responsive(True), 'showPager': responsive(True),
             'showTableStats': responsive(True), 'pageSize': responsive(page), 'tableStyle': 'S', '@width': responsive('100%')}
        if input_binding: o['queryData'] = ('dynamic', input_binding)
        if height: o['height'] = responsive(height)
        o.update(options)
        return self.ref(item_id, 'Service Data Table', self.std(title), binding=f'{binding}[]', boxes=[('ContentBox1', children)], options=o)

# CP4BA Workflow serves the product applications under a context root: /bas on the Studio (Workflow Authoring), /baw-<instance> on a
# Process Server (e.g. /baw-bawins1). Server-side REST calls of the kit (kitHttp) append every path (/rest/..., /bpm/..., /ops/...) to
# serverBaseURL, so the context root belongs in serverBaseURL only: the in-pod loopback https://localhost:9443<context root>
# (verified on CP4BA 24.0.1: Studio /bas and Process Server /baw-bawins1).
def cp4ba_default(name, value, context_root):
    """Environment variable default for target='cp4ba': the localhost:9443 loopback of serverBaseURL gets the context root."""
    if name == 'serverBaseURL' and re.fullmatch(r'https://localhost:9443/?', str(value)): return 'https://localhost:9443' + context_root
    return value

# ------------------------------------------------------------------------------------------------------ the application
class App:
    def __init__(self, name, acronym, snapshot='1.0', description='', namespace=None, sysdata_tc=False, snapshot_description='', target=None,
                 context_root=None, theme=None):
        """target = 'traditional' (default: System Data 8.6.0.0, any 8.6.2 / BAW 20-26 center) or 'cp4ba' (System Data bound to its
        8.6.0.0_TC snapshot - required on a CP4BA Studio 24-26: the 8.6.0.0 binding imports there but assetsValidation reports ErrorType 5 and
        the snapshot cannot be installed on a Process Server). Both write targetEnvironment BAW_tWAS: the Studio turns it into BAW_CP4A on
        import, while a traditional Workflow Center refuses BAW_CP4A ("can't import versions of projects intended for a container only
        environment") - so a cp4ba build also imports on BAW 20.0.0.1 and 26 (both carry 8.6.0.0_TC). Verified on 20.0.0.1, 26, CP4BA 24.0.1.
        Default from the TWXKIT_TARGET environment variable.
        context_root (cp4ba only) = the Workflow context root in the serverBaseURL default: '/bas' (Studio, default) or '/baw-<instance>'
        (Process Server); default from TWXKIT_CONTEXT_ROOT. On a Process Server the value can also be changed after the install
        (POST /ops/std/bpm/containers/<acr>/versions/<v>/env_vars {"pairs": [{"name": "serverBaseURL", "value": ...}]} - live)."""
        assert re.fullmatch(r'[A-Z0-9_]{1,7}', acronym), 'acronym: 1-7 upper-case letters / digits'
        self.target = (target or os.environ.get('TWXKIT_TARGET') or 'traditional').lower()
        assert self.target in ('traditional', 'cp4ba'), "target: 'traditional' or 'cp4ba'"
        self.context_root = '/' + (context_root or os.environ.get('TWXKIT_CONTEXT_ROOT') or '/bas').strip('/')
        self.theme = (theme or os.environ.get('TWXKIT_THEME') or 'classic').lower(); assert self.theme in THEMES, f'theme: {sorted(THEMES)}'
        self.name, self.acronym, self.snapshot, self.description = name, acronym, snapshot, description
        self.snapshot_description = snapshot_description
        self.ns = namespace or uuid.uuid5(uuid.NAMESPACE_URL, 'twxkit:' + acronym)
        self.sys_snapshot = SYSDATA_TC_SNAPSHOT if (sysdata_tc or self.target == 'cp4ba') else SYSDATA['snapshot']
        self.dep_sys = self.did('dependency', 'TWSYS'); self.dep_ui = self.did('dependency', 'SYSBPMUI')
        self.project_id = '2066.' + self.did('project'); self.branch_id = '2063.' + self.did('branch'); self.snapshot_id = '2064.' + self.did('snapshot', snapshot)
        self.objects = {}      # id -> (name, type, xml)
        self.files = {}        # files/<asset id>/<uuid> -> bytes
        self.tags = {}         # object id -> [tags]
        self.envs = []; self.bos = {}; self.flows = {}; self.cshs_ids = {}; self.view_ids = {}; self.teams = {}
        self.default_team = None
        self.flow_params = {}  # flow name -> {param: 2055. id}
        self.flow_param_types = {}  # flow name -> {param: type}
        self.cshs_params = {}  # human service name -> {param: (2055. id, base type, is list)}
        self.bpds = {}         # process name -> 25. id
        self.log = []
    # ---- ids
    def did(self, *parts): return str(uuid.uuid5(self.ns, ':'.join(str(p) for p in parts)))
    def type_ref(self, typ):
        """classRef / classId of a type name: System Data type -> '<dep>/12.x', business object of this app -> '/12.x'."""
        if typ in TYPES: return f'{self.dep_sys}/{TYPES[typ]}'
        if typ in UITK_TYPES: return f'{self.dep_ui}/{UITK_TYPES[typ]}'
        if typ in self.bos: return '/' + self.bos[typ]
        raise KeyError(f'unknown type {typ}: declare the business object first')
    def type_id(self, typ):
        """Bare '12.x' id of a type (itemSubjectRef / evaluatesToTypeRef use itm.12.x)."""
        return TYPES[typ] if typ in TYPES else UITK_TYPES[typ] if typ in UITK_TYPES else self.bos[typ]
    def type_scope(self, typ):
        """Owner of a type for render_flow: True = business object of this app, False = System Data, or the UI Toolkit dependency id."""
        return self.dep_ui if typ in UITK_TYPES else typ not in TYPES
    def flow_id(self, name):
        if name not in self.flows: raise KeyError(f'unknown flow {name}: declare it before the human service that calls it')
        return self.flows[name]
    def team_ref(self, team):
        """'All Users' / 'System' (System Data) or a team of this app (name)."""
        if team in ('All Users', TEAM_ALL_USERS): return f'{self.dep_sys}/{TEAM_ALL_USERS}'
        if team in ('System', TEAM_SYSTEM): return f'{self.dep_sys}/{TEAM_SYSTEM}'
        return '/' + self.teams[team]
    def add(self, oid, name, typ, xml, tags=()):
        assert oid not in self.objects, f'duplicate object id {oid} ({name})'
        ET.fromstring(xml.encode('utf-8'))   # well-formed or fail now
        self.objects[oid] = (name, typ, xml)
        if tags: self.tags[oid] = list(tags)
        self.log.append(f'{typ:22} {oid}  {name}')
        return oid
    @staticmethod
    def split_type(t):
        """'String' -> ('String', False); 'KSRow[]' -> ('KSRow', True)."""
        return (t[:-2], True) if t.endswith('[]') else (t, False)

    # ---- environment variables (62.)
    def env(self, name, default, description=''):
        """Environment variable with its default. KITENV_<name> in the build environment overrides the default (lab builds with real
        hosts and users - give such a build its own snapshot name, the server caches tw.env per snapshot)."""
        if self.target == 'cp4ba': default = cp4ba_default(name, default, self.context_root)
        default = os.environ.get('KITENV_' + name, default)
        assert default != '', f"environment variable {name}: the default must not be empty (the import fails on an empty value); use a placeholder such as '-' and treat it as empty in the scripts (kitEnv(name, '') does not, so compare explicitly)"
        self.envs.append((name, default, description))

    def _render_envs(self):
        oid = '62.' + self.did('envset')
        vars_xml = ''
        for name, default, description in self.envs:
            vid = '2094.' + self.did('env', name)
            defaults = ''.join(f"""            <envVarDefault>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <envVarDefaultId>2092.{self.did('envdefault', name, i)}</envVarDefaultId>
                <envTypeId>2093.{i}</envTypeId>
                <envVarId>{vid}</envVarId>
                <value>{esc(default)}</value>
                <guid>{self.did('guid', 'envdefault', name, i)}</guid>
                <versionId>{self.did('version', 'envdefault', name, i)}</versionId>
            </envVarDefault>
""" for i in range(4))
            vars_xml += f"""        <envVar name="{attr(name)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <envVarId>{vid}</envVarId>
            <envVarSetId>{oid}</envVarSetId>
            <envVarTypeId>2106.0</envVarTypeId>
            <defaultValue>{esc(default)}</defaultValue>
            <description>{esc(description)}</description>
            <guid>{self.did('guid', 'env', name)}</guid>
            <versionId>{self.did('version', 'env', name)}</versionId>
{defaults}        </envVar>
"""
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <environmentVariableSet id="{oid}" name="Environment Variables">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <envVarSetId>{oid}</envVarSetId>
        <description isNull="true" />
        <guid>{self.did('guid', 'envset')}</guid>
        <versionId>{self.did('version', 'envset')}</versionId>
{vars_xml}    </environmentVariableSet>
</teamworks>
"""
        self.add(oid, 'Environment Variables', 'environmentVariableSet', xml)

    # ---- project defaults (63.)
    def _render_defaults(self):
        oid = '63.' + self.did('projectdefaults')
        team = self.team_ref(self.default_team) if self.default_team else f'{self.dep_sys}/{TEAM_ALL_USERS}'
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <projectDefaults id="{oid}" name="Process App Settings">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <projectDefaultsId>{oid}</projectDefaultsId>
        <description isNull="true" />
        <guid>{self.did('guid', 'projectdefaults')}</guid>
        <versionId>{self.did('version', 'projectdefaults')}</versionId>
        <participantRef>{team}</participantRef>
        <defaultXslRef isNull="true" />
        <defaultCssRef isNull="true" />
        <defaultTheme>{self.dep_sys}/{THEMES[self.theme]}</defaultTheme>
        <themeVersion isNull="true" />
        <defaultJsRefs isNull="true" />
        <isWbmEnabled>false</isWbmEnabled>
        <namespace>http://{self.acronym}</namespace>
        <isIidOptimized>true</isIidOptimized>
        <isQueueBypass>1</isQueueBypass>
        <templateAcronymReference isNull="true" />
        <templateSnapshotReference isNull="true" />
        <targetEnvironment>BAW_tWAS</targetEnvironment>
    </projectDefaults>
</teamworks>
"""
        self.add(oid, 'Process App Settings', 'projectDefaults', xml)

    # ---- business objects (12.)
    def bo(self, name, fields, description=''):
        """fields = [(name, type)] with type = a System Data type name, a business object of this app, or either with '[]' for lists.
        Declare referenced business objects first (their ids are needed); self-references are allowed."""
        oid = '12.' + self.did('bo', name); self.bos[name] = oid
        self._pending_bos = getattr(self, '_pending_bos', []) + [(name, oid, fields, description)]
        return oid

    def _render_bos(self):
        for name, oid, fields, description in getattr(self, '_pending_bos', []):
            props = ''; elements = []
            for fname, ftype in fields:
                base, lst = self.split_type(ftype)
                props += f"""            <property>
                <name>{esc(fname)}</name>
                <description isNull="true" />
                <classRef>{self.type_ref(base)}</classRef>
                <arrayProperty>{'true' if lst else 'false'}</arrayProperty>
                <propertyDefault isNull="true" />
                <propertyRequired>false</propertyRequired>
                <propertyHidden>false</propertyHidden>
                <annotation type="com.lombardisoftware.core.xml.XMLFieldAnnotation" version="2.0">
                    <exclude isNull="true" />
                    <nodeType isNull="true" />
                    <name isNull="true" />
                    <namespace isNull="true" />
                    <typeName isNull="true" />
                    <typeNamespace isNull="true" />
                    <minOccurs isNull="true" />
                    <maxOccurs isNull="true" />
                    <nillable isNull="true" />
                    <order isNull="true" />
                    <wrapArray isNull="true" />
                    <arrayTypeName isNull="true" />
                    <arrayTypeAnonymous isNull="true" />
                    <arrayItemName isNull="true" />
                    <arrayItemWildcard isNull="true" />
                    <wildcard isNull="true" />
                    <wildcardVariety isNull="true" />
                    <wildcardMode isNull="true" />
                    <wildcardNamespace isNull="true" />
                    <parentModelGroupCompositor isNull="true" />
                    <timeZone isNull="true" />
                </annotation>
            </property>
"""
                e = {"annotation": {"documentation": [{}], "appinfo": [{"propertyName": [fname], "advancedParameterProperties": [{}]}]}, "name": fname}
                if lst: e["maxOccurs"] = "unbounded"
                e["type"] = f"{{http://lombardi.ibm.com/schema/}}{base}" if base in TYPES else f"{{http://SYSBPMUI}}{base}" if base in UITK_TYPES else f"{{http://{self.acronym}}}{base}"
                e["otherAttributes"] = {"{http://www.ibm.com/bpmsdk}refid": self.type_id(base)}
                elements.append(e)
            jd = {"attributeFormDefault": "unqualified", "elementFormDefault": "unqualified", "targetNamespace": f"http://{self.acronym}",
                  "complexType": [{"annotation": {"documentation": [{}], "appinfo": [{"shared": [False], "advancedProperties": [{}], "shadow": [False]}]},
                                   "sequence": {"element": elements}, "name": name}], "id": f"_{oid}"}
            xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <twClass id="{oid}" name="{attr(name)}">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <classId>{oid}</classId>
        <type>1</type>
        <isSystem>false</isSystem>
        <shared>false</shared>
        <isShadow>false</isShadow>
        <globalLifetime>false</globalLifetime>
        <internalName isNull="true" />
        <extensionType isNull="true" />
        <saveServiceRef isNull="true" />
        <bpmn2Data isNull="true" />
        <externalId>itm.{oid}</externalId>
        <dependencySummary isNull="true" />
        <jsonData>{esc(json.dumps(jd, separators=(',', ':')).replace('/', '\\/'))}</jsonData>
        <description>{esc(description)}</description>
        <guid>{self.did('guid', 'bo', name)}</guid>
        <versionId>{self.did('version', 'bo', name)}</versionId>
        <definition>
{props}            <validator>
                <className isNull="true" />
                <errorMessage isNull="true" />
                <webWidgetJavaClass isNull="true" />
                <externalType isNull="true" />
                <configData>
                    <schema>
                        <simpleType name="{attr(name)}">
                            <restriction base="String" />
                        </simpleType>
                    </schema>
                </configData>
            </validator>
            <annotation type="com.lombardisoftware.core.xml.XMLTypeAnnotation" version="2.0">
                <exclude isNull="true" />
                <anonymous isNull="true" />
                <name isNull="true" />
                <namespace isNull="true" />
                <elementName isNull="true" />
                <elementNamespace isNull="true" />
                <protoTypeName isNull="true" />
                <baseTypeName isNull="true" />
                <specialType isNull="true" />
                <contentTypeVariety isNull="true" />
                <xscRef isNull="true" />
            </annotation>
        </definition>
    </twClass>
</teamworks>
"""
            self.add(oid, name, 'twClass', xml)

    # ---- teams (24.)
    def team(self, name, users=(), groups=(), default=False):
        """Team with standard members (user logins and/or group names of the server's registry). default=True makes it the
        process app's default team (Process App Settings). TWXKIT_MEMBERS=u1,u2 in the build environment replaces the users of every
        team that lists users (the registry of the target differs: celladmin on a lab, LDAP users on CP4BA)."""
        if users and os.environ.get('TWXKIT_MEMBERS'): users = [u.strip() for u in os.environ['TWXKIT_MEMBERS'].split(',') if u.strip()]
        oid = '24.' + self.did('team', name); self.teams[name] = oid
        if default: self.default_team = name
        members = [{"name": u, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmteamext.Member"} for u in users]
        gmembers = [{"name": g, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmteamext.Member"} for g in groups]
        mem = {}
        if members: mem["Users"] = members
        if gmembers: mem["Groups"] = gmembers
        jid = '24.' + self.did('teamjson', name)
        jd = {"rootElement": [{"extensionElements": {"team": [{"members": mem, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmteamext.TTeamDetails", "type": "StandardMembers"}]},
                               "documentation": [{"content": [], "textFormat": "text/plain"}], "name": name, "declaredType": "resource", "id": jid}],
              "targetNamespace": "", "typeLanguage": "http://www.w3.org/2001/XMLSchema", "expressionLanguage": "http://www.w3.org/1999/XPath", "id": jid}
        std = ''.join(f"""            <standardMember>
                <type>{t}</type>
                <name>{esc(n)}</name>
            </standardMember>
""" for t, ns_ in (('User', users), ('Group', groups)) for n in ns_)
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <participant id="{oid}" name="{attr(name)}">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <participantId>{oid}</participantId>
        <participantDefinition isNull="true" />
        <simulationGroupSize>2</simulationGroupSize>
        <capacityType>1</capacityType>
        <definitionType>3</definitionType>
        <percentAvailable isNull="true" />
        <percentEfficiency isNull="true" />
        <cost>10.00</cost>
        <currencyCode isNull="true" />
        <image isNull="true" />
        <serviceMembersRef isNull="true" />
        <managersRef isNull="true" />
        <jsonData>{esc(json.dumps(jd, separators=(',', ':')).replace('/', '\\/'))}</jsonData>
        <externalId isNull="true" />
        <description isNull="true" />
        <guid>{self.did('guid', 'team', name)}</guid>
        <versionId>{self.did('version', 'team', name)}</versionId>
        <standardMembers>
{std}        </standardMembers>
        <teamAssignments />
    </participant>
</teamworks>
"""
        self.add(oid, name, 'participant', xml)
        return oid

    # ---- managed files (61.)
    def server_file(self, name, content, description=''):
        """Server JavaScript file: its functions are callable from every server-side script of the app (tw.* scripts of service flows).
        Ids derive from the content hash: the engine caches server files by id across delete + re-import, so changed content gets new ids."""
        return self._asset(name, content.encode('utf-8'), 'application/javascript', 'J', description)
    def web_file(self, name, data, mime='application/octet-stream', description=''):
        """Web file (image, css, js for coaches): served at /teamworks/webasset/<snapshot>/W/<name>."""
        return self._asset(name, data if isinstance(data, bytes) else data.encode('utf-8'), mime, 'W', description)
    def _asset(self, name, data, mime, code, description):
        digest = hashlib.sha1(data).hexdigest()[:12]
        oid = '61.' + self.did('asset', name, digest); au = self.did('asset-file', name, digest)
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <managedAsset id="{oid}" name="{attr(name)}">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <managedAssetId>{oid}</managedAssetId>
        <assetUuid>{au}</assetUuid>
        <mimeType>{mime}</mimeType>
        <charEncoding isNull="true" />
        <assetTypeCode>{code}</assetTypeCode>
        <length>{len(data)}</length>
        <localLastModification>{NOW}</localLastModification>
        <description>{esc(description)}</description>
        <isDocumentationFile>false</isDocumentationFile>
        <guid>{self.did('guid', 'asset', name, digest)}</guid>
        <versionId>{self.did('version', 'asset', name, digest)}</versionId>
    </managedAsset>
</teamworks>
"""
        self.add(oid, name, 'managedAsset', xml)
        self.files[f'files/{oid}/{au}'] = data
        return oid

    # ---- service flows (1., processType 12)
    def flow(self, name, inputs=(), outputs=(), variables=(), script=None, steps=None, nodes=None, edges=None, ajax=True, description=''):
        """Service flow. inputs / outputs / variables = [(name, type)] ('T[]' = list). Body: script (one script task), or
        steps = [('script', label, code) | ('call', label, other flow name, {callee input: expression}, {callee output: 'tw.local.x'})]
        (linear), or nodes + edges (see render_flow: script / call / gateway nodes, conditional edges, loops).
        A flow used by a Service Call control must name its input `data` and its output `results`."""
        fid = '1.' + self.did('flow', name); self.flows[name] = fid
        params = [(n, 'in', self.type_id(self.split_type(t)[0]), self.split_type(t)[1], self.type_scope(self.split_type(t)[0])) for n, t in inputs] + \
                 [(n, 'out', self.type_id(self.split_type(t)[0]), self.split_type(t)[1], self.type_scope(self.split_type(t)[0])) for n, t in outputs]
        vars_ = [(n, self.type_id(self.split_type(t)[0]), self.split_type(t)[1], self.type_scope(self.split_type(t)[0])) for n, t in variables]
        if nodes is None:
            if steps is None: steps = [('script', name, script or '')]
            nodes, edges = linear(self, steps)
        xml, P = render_flow(self, name, fid, params, vars_, nodes, edges, ajax, description)
        self.flow_params[name] = P; self.flow_param_types[name] = {n: t for n, t in list(inputs) + list(outputs)}
        self.add(fid, name, 'process', xml)
        return fid

    # ---- client-side human services (1., processType 10)
    def cshs(self, name, layout, variables=(), init=None, exposed='Dashboard', team='All Users', description='', css=None, inputs=(), outputs=(), exits=None):
        """Client-side human service with one coach. variables = [(name, type[, 'new' | default expression])] ('new' = an instance of the
        business object is created at start); init = name of a service flow whose outputs are copied into variables of the same name at
        start (server side: environment variables, current user, lookups); layout = function(L) -> [layout items] (L = Layout);
        exposed = 'Dashboard' (Process Portal dashboard, playback URL executecf?modelID=<id>&branchID=<branch>) or None;
        css = extra CSS for the coach (rendered as a small coach view "style").
        Task implementation (the human service a process user task calls): inputs / outputs = [(name, type)] become the service
        parameters (available as tw.local.<name> in the coach) and exposed=None; exits = {button item id: script or None} wires each
        button to the End node through a coach boundary event (an optional script task in between, e.g. 'tw.local.decision = "approve";'),
        which completes the task. Buttons named in exits are created with on_click=None (the boundary event is their click)."""
        fid = '1.' + self.did('cshs', name); self.cshs_ids[name] = fid
        did = lambda *p: self.did('cshs', name, *p)
        params = [(n, 'in', t) for n, t in inputs] + [(n, 'out', t) for n, t in outputs]
        P = {(n, d): '2055.' + did('param', d, n) for n, d, t in params}   # the same name may be an input and an output (in / out idiom)
        self.cshs_params[name] = {(n, d): (P[(n, d)], self.split_type(t)[0], self.split_type(t)[1]) for n, d, t in params}
        param_xml = ''.join(f"""        <processParameter name="{attr(n)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processParameterId>{P[(n, d)]}</processParameterId>
            <processId>{fid}</processId>
            <parameterType>{1 if d == 'in' else 2}</parameterType>
            <isArrayOf>{'true' if self.split_type(t)[1] else 'false'}</isArrayOf>
            <classId>{self.type_ref(self.split_type(t)[0])}</classId>
            <seq>{i + 1}</seq>
            <hasDefault>false</hasDefault>
            <defaultValue isNull="true" />
            <isLocked>false</isLocked>
            <description isNull="true" />
            <guid>{did('guid', 'param', n)}</guid>
            <versionId>{did('version', 'param', n)}</versionId>
        </processParameter>
""" for i, (n, d, t) in enumerate(params))
        if params:
            io_xml = ('                    <ns17:ioSpecification>\n'
                      + ''.join(f'                        <ns17:data{"Input" if d == "in" else "Output"} name="{attr(n)}" itemSubjectRef="itm.{self.type_id(self.split_type(t)[0])}" isCollection="{"true" if self.split_type(t)[1] else "false"}" id="{P[(n, d)]}" />\n' for n, d, t in params)
                      + f'                        <ns17:inputSet id="{did("inputset")}">' + ''.join(f'<ns17:dataInputRefs>{P[(n, d)]}</ns17:dataInputRefs>' for n, d, t in params if d == 'in') + '</ns17:inputSet>\n'
                      + f'                        <ns17:outputSet id="{did("outputset")}">' + ''.join(f'<ns17:dataOutputRefs>{P[(n, d)]}</ns17:dataOutputRefs>' for n, d, t in params if d == 'out') + '</ns17:outputSet>\n'
                      + '                    </ns17:ioSpecification>\n')
        else:
            io_xml = f"""                    <ns17:ioSpecification>
                        <ns17:inputSet id="{did('inputset')}" />
                        <ns17:outputSet id="{did('outputset')}" />
                    </ns17:ioSpecification>
"""
        exits = dict(exits or {})
        vars_ = []
        for v in variables:
            vn, vt = v[0], v[1]; base, lst = self.split_type(vt); default = v[2] if len(v) > 2 else None
            if default == 'new': default = f'var autoObject = new tw.object.{base}();\nautoObject' if base in self.bos else None
            vars_.append((vn, base, lst, default))
        if 'statusMessage' not in [v[0] for v in vars_]: vars_.insert(0, ('statusMessage', 'String', False, None))
        pv = ''.join(f"""        <processVariable name="{attr(vn)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processVariableId>2056.{did('var', vn)}</processVariableId>
            <description isNull="true" />
            <processId>{fid}</processId>
            <namespace>2</namespace>
            <seq>{i + 1}</seq>
            <isArrayOf>{'true' if lst else 'false'}</isArrayOf>
            <isTransient>false</isTransient>
            <classId>{self.type_ref(base)}</classId>
            <hasDefault>{'true' if default else 'false'}</hasDefault>
            {'<defaultValue>' + esc(default) + '</defaultValue>' if default else '<defaultValue isNull="true" />'}
            <guid>{did('guid', 'var', vn)}</guid>
            <versionId>{did('version', 'var', vn)}</versionId>
        </processVariable>
""" for i, (vn, base, lst, default) in enumerate(vars_))
        data_objects = ''.join(f'                            <ns17:dataObject itemSubjectRef="itm.{self.type_id(base)}" isCollection="{"true" if lst else "false"}" name="{attr(vn)}" id="2056.{did("var", vn)}" />\n' for vn, base, lst, default in vars_)
        # ---- layout
        L = Layout(self, 'ns18', 'cshs:' + name)
        items = layout(L)
        if css:
            style_id = self.coach_view(name + ' style', css=css)
            items = [L.custom('style1', style_id)] + list(items)
        page = L.vlayout('Page', items, label=name, top=True)
        dup = [i for i in set(L.item_ids) if L.item_ids.count(i) > 1]
        assert not dup, f'layout item ids must be unique within the coach: {dup}'
        # ---- nodes: start -> [init call] -> coach ; end
        wrapper = did('item', 'coachflow'); end_item = did('item', 'end'); init_item = did('item', 'init')
        start_ev = did('node', 'start'); coach_node = did('node', 'coach'); end_ev = did('node', 'end')
        f_start = '2027.' + did('flow', 'start'); f_init = '2027.' + did('flow', 'init')
        coach_incoming = f_init if init else f_start
        start_target = f'2025.{init_item}' if init else f'2025.{coach_node}'
        # exits: coach --(boundary event of a button)--> [script task] --> End
        exit_xml = ''; coach_outgoing = ''; end_incoming = ''
        for ei, (btn, script) in enumerate(exits.items()):
            f_exit = '2027.' + did('flow', 'exit', btn); f_exit2 = '2027.' + did('flow', 'exit2', btn); s_node = did('node', 'exit', btn)
            target = f'2025.{s_node}' if script else end_ev
            coach_outgoing += f'                                <ns17:outgoing>{f_exit}</ns17:outgoing>\n'
            end_incoming += f'                                <ns17:incoming>{f_exit2 if script else f_exit}</ns17:incoming>\n'
            link = lambda src, dst, fl, nm, binding='': f"""                            <ns17:sequenceFlow sourceRef="{src}" targetRef="{dst}" name="{attr(nm)}" id="{fl}">
                                <ns17:extensionElements>
                                    <ns3:sequenceFlowImplementation sboSyncEnabled="true" />
                                    <ns13:linkVisualInfo>
                                        <ns13:sourcePortLocation>rightCenter</ns13:sourcePortLocation>
                                        <ns13:targetPortLocation>leftCenter</ns13:targetPortLocation>
                                        <ns13:showLabel>false</ns13:showLabel>
                                        <ns13:showCoachControlLabel>true</ns13:showCoachControlLabel>
                                        <ns13:labelPosition>0.0</ns13:labelPosition>
                                        <ns13:saveExecutionContext>true</ns13:saveExecutionContext>
                                    </ns13:linkVisualInfo>{binding}
                                </ns17:extensionElements>
                            </ns17:sequenceFlow>
"""
            binding = f'\n                                    <ns3:coachEventBinding id="{did("binding", btn)}"><ns3:coachEventPath>{attr(btn)}</ns3:coachEventPath></ns3:coachEventBinding>'
            exit_xml += link(f'2025.{coach_node}', target, f_exit, btn, binding)
            if script:
                exit_xml += f"""                            <ns17:scriptTask scriptFormat="text/x-javascript" default="{f_exit2}" name="{attr(btn)}" id="2025.{s_node}">
                                <ns17:extensionElements>
                                    <ns13:nodeVisualInfo x="{560 if init else 400}" y="{100 + 90 * ei}" width="95" height="70" />
                                </ns17:extensionElements>
                                <ns17:incoming>{f_exit}</ns17:incoming>
                                <ns17:outgoing>{f_exit2}</ns17:outgoing>
                                <ns17:script>{esc(script)}</ns17:script>
                            </ns17:scriptTask>
""" + link(f'2025.{s_node}', end_ev, f_exit2, 'To End')
        init_xml = ''; init_item_xml = ''
        if init:
            P = self.flow_params[init]; iid = self.flow_id(init)
            outs = [(pn, pid) for pn, pid in P.items() if pn in [v[0] for v in vars_]]
            assert outs, f'init flow {init}: no output parameter matches a variable of {name}'
            vtype = {v[0]: (v[1], v[2]) for v in vars_}
            assoc = ''.join(f'<ns17:dataOutputAssociation><ns17:sourceRef>{pid}</ns17:sourceRef><ns17:assignment><ns17:to xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns17:tFormalExpression" evaluatesToTypeRef="itm.{self.type_id(vtype[pn][0])}">tw.local.{pn}</ns17:to></ns17:assignment></ns17:dataOutputAssociation>' for pn, pid in outs)
            init_xml = f"""                            <ns17:callActivity calledElement="{iid}" default="{f_init}" name="{attr(init)}" id="2025.{init_item}">
                                <ns17:extensionElements>
                                    <ns13:nodeVisualInfo x="200" y="177" width="95" height="70" />
                                </ns17:extensionElements>
                                <ns17:incoming>{f_start}</ns17:incoming>
                                <ns17:outgoing>{f_init}</ns17:outgoing>
                            {assoc}</ns17:callActivity>
                            <ns17:sequenceFlow sourceRef="2025.{init_item}" targetRef="2025.{coach_node}" name="To The Coach" id="{f_init}">
                                <ns17:extensionElements>
                                    <ns13:linkVisualInfo>
                                        <ns13:sourcePortLocation>rightCenter</ns13:sourcePortLocation>
                                        <ns13:targetPortLocation>leftCenter</ns13:targetPortLocation>
                                        <ns13:showLabel>false</ns13:showLabel>
                                        <ns13:showCoachControlLabel>false</ns13:showCoachControlLabel>
                                        <ns13:labelPosition>0.0</ns13:labelPosition>
                                        <ns13:saveExecutionContext>false</ns13:saveExecutionContext>
                                    </ns13:linkVisualInfo>
                                </ns17:extensionElements>
                            </ns17:sequenceFlow>
"""
            sub = '3012.' + did('component', 'init')
            maps = ''.join(f"""                <parameterMapping name="{attr(pn)}">
                    <lastModified isNull="true" />
                    <lastModifiedBy isNull="true" />
                    <parameterMappingId>2054.{did('mapping', pn)}</parameterMappingId>
                    <processParameterId>{pid}</processParameterId>
                    <parameterMappingParentId>{sub}</parameterMappingParentId>
                    <useDefault>false</useDefault>
                    <value>tw.local.{pn}</value>
                    <classRef>{self.type_ref(vtype[pn][0])}</classRef>
                    <isList>{'true' if vtype[pn][1] else 'false'}</isList>
                    <isInput>false</isInput>
                    <guid>{did('guid', 'mapping', pn)}</guid>
                    <versionId>{did('version', 'mapping', pn)}</versionId>
                    <description isNull="true" />
                </parameterMapping>
""" for pn, pid in outs)
            init_item_xml = f"""        <item>
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processItemId>2025.{init_item}</processItemId>
            <processId>{fid}</processId>
            <name>{attr(init)}</name>
            <tWComponentName>SubProcess</tWComponentName>
            <tWComponentId>{sub}</tWComponentId>
            <isLogEnabled>false</isLogEnabled>
            <isTraceEnabled>false</isTraceEnabled>
            <traceCategory isNull="true" />
            <traceLevel isNull="true" />
            <traceMessage isNull="true" />
            <traceSymbolTable isNull="true" />
            <isExecutionContextTraced>false</isExecutionContextTraced>
            <saveExecutionContext>true</saveExecutionContext>
            <documentation isNull="true" />
            <isErrorHandlerEnabled>false</isErrorHandlerEnabled>
            <errorHandlerItemId isNull="true" />
            <guid>{legacy_guid(did('guid', 'item', 'init'))}</guid>
            <versionId>{did('version', 'item', 'init')}</versionId>
            <externalServiceRef isNull="true" />
            <externalServiceOp isNull="true" />
            <nodeColor isNull="true" />
            <layoutData x="0" y="0">
                <errorLink>
                    <controlPoints />
                    <showEndState>false</showEndState>
                    <showName>false</showName>
                </errorLink>
            </layoutData>
            <TWComponent>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <subProcessId>{sub}</subProcessId>
                <attachedProcessRef>/{iid}</attachedProcessRef>
                <guid>{did('guid', 'component', 'init')}</guid>
                <versionId>{did('version', 'component', 'init')}</versionId>
{maps}            </TWComponent>
        </item>
"""
        def item(pid, label, component, cid, tw):
            return f"""        <item>
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processItemId>2025.{pid}</processItemId>
            <processId>{fid}</processId>
            <name>{label}</name>
            <tWComponentName>{component}</tWComponentName>
            <tWComponentId>{cid}</tWComponentId>
            <isLogEnabled>false</isLogEnabled>
            <isTraceEnabled>false</isTraceEnabled>
            <traceCategory isNull="true" />
            <traceLevel isNull="true" />
            <traceMessage isNull="true" />
            <traceSymbolTable isNull="true" />
            <isExecutionContextTraced>false</isExecutionContextTraced>
            <saveExecutionContext>true</saveExecutionContext>
            <documentation isNull="true" />
            <isErrorHandlerEnabled>false</isErrorHandlerEnabled>
            <errorHandlerItemId isNull="true" />
            <guid>{legacy_guid(did('guid', 'item', pid))}</guid>
            <versionId>{did('version', 'item', pid)}</versionId>
            <externalServiceRef isNull="true" />
            <externalServiceOp isNull="true" />
            <nodeColor isNull="true" />
            <layoutData x="0" y="0">
                <errorLink>
                    <controlPoints />
                    <showEndState>false</showEndState>
                    <showName>false</showName>
                </errorLink>
            </layoutData>
            {tw}
        </item>
"""
        end_cid = '3008.' + did('component', 'end')
        end_tw = f"""<TWComponent>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <exitPointId>{end_cid}</exitPointId>
                <haltProcess>false</haltProcess>
                <guid>{did('guid', 'component', 'end')}</guid>
                <versionId>{did('version', 'component', 'end')}</versionId>
            </TWComponent>"""
        items_xml = item(end_item, 'End', 'ExitPoint', end_cid, end_tw) + init_item_xml + item(wrapper, 'CoachFlowWrapper', 'CoachFlow', '3032.' + did('component', 'coachflow'), '<TWComponent />')
        team_ref = self.team_ref(team)
        exposed_xml = f'\n                        <ns3:exposedAs>{exposed or "NotExposed"}</ns3:exposedAs>'
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <process id="{fid}" name="{attr(name)}">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <processId>{fid}</processId>
        <image isNull="true" />
        <tabGroup isNull="true" />
        <startingProcessItemId>2025.{wrapper}</startingProcessItemId>
        <isRootProcess>false</isRootProcess>
        <processType>10</processType>
        <isErrorHandlerEnabled>false</isErrorHandlerEnabled>
        <errorHandlerItemId isNull="true" />
        <isLoggingVariables>false</isLoggingVariables>
        <isTransactional>false</isTransactional>
        <processTimingLevel isNull="true" />
        <participantRef>{team_ref}</participantRef>
        <exposedType>{3 if exposed else 0}</exposedType>
        <isTrackingEnabled>true</isTrackingEnabled>
        <xmlData isNull="true" />
        <cachingType>false</cachingType>
        <itemLabel isNull="true" />
        <cacheLength isNull="true" />
        <mobileReady>true</mobileReady>
        <sboSyncEnabled>true</sboSyncEnabled>
        <externalId isNull="true" />
        <isSecured>false</isSecured>
        <isAjaxExposed>false</isAjaxExposed>
        <description>{esc(description)}</description>
        <guid>{did('guid', 'process')}</guid>
        <versionId>{did('version', 'process')}</versionId>
{param_xml}        <dependencySummary isNull="true" />
        <jsonData isNull="true" />
        <field1 isNull="true" />
        <field2 isNull="true" />
        <field3>0</field3>
        <field4 isNull="true" />
        <field5>false</field5>
        <clobField1 isNull="true" />
        <blobField1 isNull="true" />
{pv}{items_xml}        <startingProcessItemId>2025.{wrapper}</startingProcessItemId>
        <errorHandlerItemId isNull="true" />
        <layoutData noConversion="true">
            <errorLink>
                <controlPoints />
                <showEndState>false</showEndState>
                <showName>false</showName>
            </errorLink>
        </layoutData>
        <startPoint>
            <layoutData x="0" y="0">
                <errorLink>
                    <controlPoints />
                    <showEndState>false</showEndState>
                    <showName>false</showName>
                </errorLink>
            </layoutData>
        </startPoint>
        <startLink>
            <fromPort locationId="rightCenter" portType="1" />
            <toPort locationId="leftCenter" portType="2" />
            <layoutData>
                <controlPoints />
                <showEndState>false</showEndState>
                <showName>false</showName>
            </layoutData>
        </startLink>
        <coachflow>
            <ns17:definitions {BPMN_NS} id="{did('definitions')}" targetNamespace="" expressionLanguage="http://www.ibm.com/xmlns/prod/bpm/expression-lang/javascript">
                <ns17:globalUserTask name="{attr(name)}" id="{fid}">
                    <ns17:documentation />
                    <ns17:extensionElements>
                        <ns3:userTaskImplementation id="{did('implementation')}">
                            <ns17:startEvent name="Start" id="{start_ev}">
                                <ns17:extensionElements>
                                    <ns13:nodeVisualInfo x="50" y="200" width="24" height="24" color="#F8F8F8" />
                                </ns17:extensionElements>
                                <ns17:outgoing>{f_start}</ns17:outgoing>
                            </ns17:startEvent>
                            <ns3:formTask name="The Coach" id="2025.{coach_node}">
                                <ns17:extensionElements>
                                    <ns13:nodeVisualInfo x="{380 if init else 220}" y="177" width="95" height="70" />
                                    <ns3:postAssignmentScript>tw.local.statusMessage = "";</ns3:postAssignmentScript>
                                </ns17:extensionElements>
                                <ns17:incoming>{coach_incoming}</ns17:incoming>
{coach_outgoing}                                <ns3:formDefinition>
                                    <ns18:coachDefinition>
                                        <ns18:layout>
                                            {page}
                                        </ns18:layout>
                                    </ns18:coachDefinition>
                                </ns3:formDefinition>
                            </ns3:formTask>
                            <ns17:endEvent name="End" id="{end_ev}">
                                <ns17:extensionElements>
                                    <ns13:nodeVisualInfo x="{720 if exits else (560 if init else 400)}" y="200" width="24" height="24" color="#F8F8F8" />
                                    <ns3:navigationInstructions>
                                        <ns3:targetType>Default</ns3:targetType>
                                    </ns3:navigationInstructions>
                                </ns17:extensionElements>
{end_incoming}                            </ns17:endEvent>
                            <ns17:sequenceFlow sourceRef="{start_ev}" targetRef="{start_target}" name="To Coach" id="{f_start}">
                                <ns17:extensionElements>
                                    <ns13:linkVisualInfo>
                                        <ns13:sourcePortLocation>rightCenter</ns13:sourcePortLocation>
                                        <ns13:targetPortLocation>leftCenter</ns13:targetPortLocation>
                                        <ns13:showLabel>false</ns13:showLabel>
                                        <ns13:showCoachControlLabel>false</ns13:showCoachControlLabel>
                                        <ns13:labelPosition>0.0</ns13:labelPosition>
                                        <ns13:saveExecutionContext>false</ns13:saveExecutionContext>
                                    </ns13:linkVisualInfo>
                                </ns17:extensionElements>
                            </ns17:sequenceFlow>
{data_objects}{init_xml}{exit_xml}                            <ns3:htmlHeaderTag id="{did('viewport')}">
                                <ns3:tagName>viewport</ns3:tagName>
                                <ns3:content>width=device-width,initial-scale=1.0</ns3:content>
                                <ns3:enabled>true</ns3:enabled>
                            </ns3:htmlHeaderTag>
                        </ns3:userTaskImplementation>
                        <ns3:mobileReady>true</ns3:mobileReady>
                        <ns3:isEmbedded>false</ns3:isEmbedded>
                        <ns3:participantRef>{team_ref.split('/')[-1]}</ns3:participantRef>{exposed_xml}
                    </ns17:extensionElements>
{io_xml}                </ns17:globalUserTask>
            </ns17:definitions>
        </coachflow>
        <link name="Untitled">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processLinkId>2027.{did('link', 'wrapper-end')}</processLinkId>
            <processId>{fid}</processId>
            <description isNull="true" />
            <fromProcessItemId>2025.{wrapper}</fromProcessItemId>
            <endStateId>Out</endStateId>
            <toProcessItemId>2025.{end_item}</toProcessItemId>
            <guid>{did('guid', 'link', 'wrapper-end')}</guid>
            <versionId>{did('version', 'link', 'wrapper-end')}</versionId>
            <layoutData>
                <controlPoints />
                <showEndState>false</showEndState>
                <showName>false</showName>
            </layoutData>
            <fromItemPort locationId="rightCenter" portType="1" />
            <toItemPort locationId="rightCenter" portType="2" />
            <fromProcessItemId>2025.{wrapper}</fromProcessItemId>
            <toProcessItemId>2025.{end_item}</toProcessItemId>
        </link>
    </process>
</teamworks>
"""
        self.add(fid, name, 'process', xml, tags=['Dashboard'] if exposed == 'Dashboard' else ())
        return fid

    # ---- business processes (25.)
    def _bpd_type(self, typ):
        """Type name -> id in the BPD renderer's convention: System Data '12.x' (dependency prefix added there), business object '/12.x'."""
        base = self.split_type(typ)[0]
        if base in TYPES: return TYPES[base]
        if base in self.bos: return '/' + self.bos[base]
        raise KeyError(f'unknown type {typ}: declare the business object first')
    def _bpd_team(self, team):
        if team in ('All Users', TEAM_ALL_USERS): return TEAM_ALL_USERS
        if team in ('System', TEAM_SYSTEM): return TEAM_SYSTEM
        if team in self.teams: return '/' + self.teams[team]
        raise KeyError(f'unknown team {team}: declare it with team() first')
    def bpd(self, name, lanes, nodes, flows, inputs=(), variables=(), searchable=(), exposed_team='All Users', instance_name=None, description=''):
        """Business process (BPD). lanes = [(name, team[, height])] top to bottom (team 'System' = system lane; other teams: 'All Users' or a
        team of this app); nodes = [dict(key, kind, name, lane, ...)] with kind start | end | timer (hours= / minutes= / custom='tw.local.date')
        | boundary (timer attached to an activity: attach=<user / service / script node key>, hours= / minutes= / custom= like timer,
        interrupting=False (default: the activity keeps running, the timer adds a token; True = the timer cancels the activity); x / y
        default to the bottom edge of the activity; flows leave it like any node, nothing flows into it)
        | script (script=) | service (callee=<flow name>, inputs={param: expression}, outputs={param: variable}) | user (callee=<human service
        name built with cshs(inputs=, outputs=, exits=)>, inputs= / outputs= like service, priority=, due_hours=, subject=, narrative=) |
        gateway (exclusive; the flow without a condition is the default) | parallel; flows = [(src, dst[, name[, condition]])].
        Diagram: x / y are optional. y is measured from the top of the node's lane (the designer draws every node at lane top + y - an
        absolute y puts the node outside its lane); without coordinates nodes are laid out left to right in list order (150 px columns)
        and centred in their lane. inputs = [(name, type[, default expression])] (process start parameters, also the REST start params),
        variables = [(name, type)] private variables, searchable = [(alias, variable, path, type)] business data for the task / instance
        search. Returns the 25. id; the ids file lists the REST start URL."""
        bid = '25.' + self.did('bpd', name); self.bpds[name] = bid
        L = []; y = 0
        for l in lanes:
            d = dict(l) if isinstance(l, dict) else dict(zip(('name', 'team', 'height'), l))
            d.setdefault('key', d['name']); d.setdefault('height', BPD_LANE_HEIGHT); d.setdefault('system', d['team'] in ('System', TEAM_SYSTEM))
            d['y'] = y; y += d['height'] + 1; d['team'] = self._bpd_team(d['team']); L.append(d)
        lane_of = {l['key']: l for l in L}
        N = []
        for i, n in enumerate(nodes):
            n = dict(n); k = n['kind']
            if k not in BPD_SIZE: raise ValueError(f"node {n['key']}: unknown kind {k} (start, end, timer, boundary, script, service, user, gateway, parallel)")
            if k == 'boundary':
                host = [m for m in nodes if m['key'] == n.get('attach')]
                if not host or host[0]['kind'] not in ('user', 'service', 'script'): raise KeyError(f"node {n['key']}: attach= must name a user / service / script node")
                if host[0]['lane'] != n['lane']: raise ValueError(f"node {n['key']}: a boundary event lives in the lane of its activity ({host[0]['lane']})")
                if any(f[1] == n['key'] for f in flows): raise ValueError(f"node {n['key']}: nothing flows into a boundary event")
            if n['lane'] not in lane_of: raise KeyError(f"node {n['key']}: unknown lane {n['lane']}")
            lane = lane_of[n['lane']]; w, h = BPD_SIZE[k]
            if k == 'boundary':   # default position: on the bottom edge of the activity (list the activity first), a little apart per attached event
                act = [m for m in N if m['key'] == n['attach']]
                if not act: raise ValueError(f"node {n['key']}: list the boundary event after its activity {n['attach']}")
                nth = sum(1 for m in N if m.get('attach') == n['attach'])
                n.setdefault('x', act[0]['x'] + 20 + 28 * nth); n.setdefault('y', min(lane['height'] - h, act[0]['y'] + 58))
            n.setdefault('x', BPD_LEFT + BPD_COLUMN * i); n.setdefault('y', max(0, (lane['height'] - h) // 2))
            if n['y'] < 0 or n['y'] + h > lane['height']:
                raise ValueError(f"node {n['key']}: y={n['y']} (+{h}) is outside lane {n['lane']} (height {lane['height']}); y is relative to the lane top")
            if k in ('user', 'service'):
                if k == 'user':
                    if n['callee'] not in self.cshs_ids: raise KeyError(f"node {n['key']}: callee {n['callee']} is not a human service of this app (cshs(..., inputs=, outputs=))")
                    P = self.cshs_params[n['callee']]; n['callee'] = self.cshs_ids[n['callee']]
                    pin = {pn: (pid, base) for (pn, d), (pid, base, lst) in P.items() if d == 'in'}; pout = {pn: (pid, base) for (pn, d), (pid, base, lst) in P.items() if d == 'out'}
                else:
                    if n['callee'] not in self.flows: raise KeyError(f"node {n['key']}: callee {n['callee']} is not a flow of this app")
                    fp = self.flow_params[n['callee']]; ft = self.flow_param_types[n['callee']]; n['callee'] = self.flows[n['callee']]
                    pin = {pn: (fp[pn], self.split_type(ft[pn])[0]) for pn in ft}; pout = pin
                ins = n.get('inputs') or {}; outs = n.get('outputs') or {}
                for pn in ins:
                    if pn not in pin: raise KeyError(f"node {n['key']}: input {pn} is not declared by the callee ({sorted(pin)})")
                for pn in outs:
                    if pn not in pout: raise KeyError(f"node {n['key']}: output {pn} is not declared by the callee ({sorted(pout)})")
                n['inputNames'] = list(ins); n['inputs'] = [(pin[pn][0], expr, self._bpd_type(pin[pn][1])) for pn, expr in ins.items()]
                n['outputs'] = [(pout[pn][0], var, self._bpd_type(pout[pn][1])) for pn, var in outs.items()]
            N.append(n)
        keys = {n['key'] for n in N}; F = []
        for i, f in enumerate(flows):
            f = list(f); src, dst = f[0], f[1]
            if src not in keys or dst not in keys: raise KeyError(f'flow {src} -> {dst}: unknown node')
            nm = f[2] if len(f) > 2 else ''; cond = f[3] if len(f) > 3 else None
            s_lane, d_lane = lane_of[[n for n in N if n['key'] == src][0]['lane']]['y'], lane_of[[n for n in N if n['key'] == dst][0]['lane']]['y']
            port = f[4] if len(f) > 4 else ('topCenter' if d_lane < s_lane else 'bottomCenter' if d_lane > s_lane else 'rightCenter')
            F.append((f'f{i}-{src}-{dst}', src, dst, nm, cond, port))
        DEFAULTS = {'String': '""', 'Integer': '0', 'Decimal': '0', 'Boolean': 'false', 'Date': 'new Date()', 'Time': 'new Date()'}
        I = []
        for x in inputs:
            base = self.split_type(x[1])[0]
            dv = x[2] if len(x) > 2 else DEFAULTS.get(base, f'new tw.object.{base}()' if base in self.bos else 'null')
            I.append((x[0], self._bpd_type(x[1]), dv))
        V = [(v[0], self._bpd_type(v[1])) for v in variables]
        SF = [(alias, var, path, self._bpd_type(t)) for alias, var, path, t in searchable]
        xml = render_bpd(self, name, bid, N, F, L, I, V, SF, self._bpd_team(exposed_team) if exposed_team else None, instance_name, description)
        self.add(bid, name, 'bpd', xml)
        return bid

    # ---- coach views (64.)
    def coach_view(self, name, layout=None, js=None, css=None, html=None, binding=None, options=(), description=''):
        """Custom coach view. layout = function(L) -> [items] (L = Layout with ns 'ns2') or None (code-only view); js / css / html =
        inline script blocks (js runs with `this` = the view instance; handlers `this.load = function () {...}` work because the
        view has isPrototypeFunc=false and no event helper); binding = ('name', type) of the data binding; options = [(name, type)]
        configuration options (tw.options.<name> in the layout, this.context.options.<name>.get('value') in code)."""
        oid = '64.' + self.did('view', name); self.view_ids[name] = oid
        did = lambda *p: self.did('view', name, *p)
        lay = '<layout isNull="true" />'
        if layout:
            L = Layout(self, 'ns2', 'view:' + name); items = layout(L)
            root = L.vlayout('Root', items, label=name, top=True)
            lay = '<layout>' + esc('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><ns2:layout xmlns:ns2="http://www.ibm.com/bpm/CoachDesignerNG" xmlns:ns3="http://www.ibm.com/bpm/coachview">' + root + '</ns2:layout>') + '</layout>'
        bind = ''
        if binding:
            bn, bt = binding; base, lst = self.split_type(bt)
            bind = f"""        <bindingType name="{attr(bn)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <coachViewBindingTypeId>65.{did('binding')}</coachViewBindingTypeId>
            <coachViewId>{oid}</coachViewId>
            <isList>{'true' if lst else 'false'}</isList>
            <classId>{self.type_ref(base)}</classId>
            <seq>0</seq>
            <description isNull="true" />
            <guid>{did('guid', 'binding')}</guid>
            <versionId>{did('version', 'binding')}</versionId>
        </bindingType>
"""
        opts = ''
        for i, (on, ot) in enumerate(options):
            base, lst = self.split_type(ot)
            opts += f"""        <configOption name="{attr(on)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <coachViewConfigOptionId>66.{did('option', on)}</coachViewConfigOptionId>
            <coachViewId>{oid}</coachViewId>
            <isList>{'true' if lst else 'false'}</isList>
            <propertyType>OBJECT</propertyType>
            <label>{attr(on)}</label>
            <classId>{self.type_ref(base)}</classId>
            <processId isNull="true" />
            <actionflowId isNull="true" />
            <isAdaptive>false</isAdaptive>
            <seq>{i}</seq>
            <description isNull="true" />
            <groupName isNull="true" />
            <guid>{did('guid', 'option', on)}</guid>
            <versionId>{did('version', 'option', on)}</versionId>
        </configOption>
"""
        scripts = ''
        for i, (label, kind, code) in enumerate([('Inline Javascript', 'JS', js), ('Inline CSS', 'CSS', css), ('Inline HTML', 'HTML', html)]):
            if not code: continue
            scripts += f"""        <inlineScript name="{label}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <coachViewInlineScriptId>68.{did('script', kind)}</coachViewInlineScriptId>
            <coachViewId>{oid}</coachViewId>
            <scriptType>{kind}</scriptType>
            <scriptBlock>{esc(code)}</scriptBlock>
            <seq>{i}</seq>
            <description isNull="true" />
            <guid>{did('guid', 'script', kind)}</guid>
            <versionId>{did('version', 'script', kind)}</versionId>
        </inlineScript>
"""
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <coachView id="{oid}" name="{attr(name)}">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <coachViewId>{oid}</coachViewId>
        <isTemplate>false</isTemplate>
        {lay}
        <paletteIcon isNull="true" />
        <previewImage isNull="true" />
        <hasLabel>false</hasLabel>
        <labelPosition>0</labelPosition>
        <nineSliceX1Coord>0</nineSliceX1Coord>
        <nineSliceX2Coord>0</nineSliceX2Coord>
        <nineSliceY1Coord>0</nineSliceY1Coord>
        <nineSliceY2Coord>0</nineSliceY2Coord>
        <emitBoundary>false</emitBoundary>
        <isPrototypeFunc>false</isPrototypeFunc>
        <enableDevMode>false</enableDevMode>
        <isMobileReady>true</isMobileReady>
        <loadJsFunction isNull="true" />
        <unloadJsFunction isNull="true" />
        <viewJsFunction isNull="true" />
        <changeJsFunction isNull="true" />
        <collaborationJsFunction isNull="true" />
        <description>{esc(description)}</description>
        <validateJsFunction isNull="true" />
        <previewAdvHtml isNull="true" />
        <previewAdvJs isNull="true" />
        <useUrlBinding>false</useUrlBinding>
        <guid>{did('guid')}</guid>
        <versionId>{did('version')}</versionId>
        <field1 isNull="true" />
        <field2 isNull="true" />
        <field3>0</field3>
        <field4 isNull="true" />
        <field5>false</field5>
        <clobField1 isNull="true" />
{bind}{opts}{scripts}    </coachView>
</teamworks>
"""
        self.add(oid, name, 'coachView', xml)
        return oid

    # ---- package
    def package_xml(self):
        objs = ''.join(f'        <object id="{oid}" versionId="{own_version(xml).group(1)}" name="{attr(name)}" type="{typ}"/>\n' for oid, (name, typ, xml) in self.objects.items())
        files = ''.join(f'        <file path="{p.split("/")[-1]}" id="{p.split("/")[1]}"/>\n' for p in self.files)
        created = datetime.datetime.now().astimezone().strftime('%Y-%m-%dT%H:%M:%S.000%z'); created = created[:-2] + ':' + created[-2:]
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:package buildId="BPM8600-20200613-172549" buildVersion="8.6.2" buildDescription="IBM Business Process Manager V8.6.2.20001 - 20200613_1807 - BPM8600-20200613-172549" containsECM="false" containsBPMN2="false" xmlns:p="http://lombardisoftware.com/schema/teamworks/7.0.0/package.xsd">
    <target>
        <project id="{self.project_id}" name="{attr(self.name)}" description="{attr(self.description)}" shortName="{self.acronym}" isToolkit="false" isHidden="false" isSystem="false" solutionID="" solutionServerName="" solutionPrefix="" type="" isTemplate="false" isIconSet="false"/>
        <branch id="{self.branch_id}" name="Main" acronym="M" description=""/>
        <snapshot id="{self.snapshot_id}" name="{attr(self.snapshot)}" acronym="{attr(self.snapshot)}" originalCreationDate="{created}" description="{attr(self.snapshot_description)}"/>
    </target>
    <governanceAssignments/>
    <dependencies>
        <dependency rank="0" isManaged="false" id="2069.{self.dep_sys}">
            <project id="{SYSDATA['project']}" name="{SYSDATA['name']}" shortName="{SYSDATA['acronym']}" isToolkit="true" isHidden="false" isSystem="true"/>
            <branch id="{SYSDATA['branch']}" name="Main"/>
            <snapshot id="{self.sys_snapshot}" name="{SYSDATA['version'] + ('_TC' if self.sys_snapshot == SYSDATA_TC_SNAPSHOT else '')}" originalCreationDate="{SYSDATA['created']}"/>
        </dependency>
        <dependency rank="1" isManaged="false" id="2069.{self.dep_ui}">
            <project id="{UITK['project']}" name="{UITK['name']}" shortName="{UITK['acronym']}" isToolkit="true" isHidden="false" isSystem="true"/>
            <branch id="{UITK['branch']}" name="Main"/>
            <snapshot id="{UITK['snapshot']}" name="{UITK['version']}" originalCreationDate="{UITK['created']}"/>
        </dependency>
    </dependencies>
    <objects>
{objs}    </objects>
    <files>
{files}    </files>
    <migrationPolicies/>
</p:package>
"""
    def metadata_xml(self):
        body = ''.join(f'    <object id="{oid}">\n        <tags>\n' + ''.join(f'            <tag>{esc(t)}</tag>\n' for t in tags) + '        </tags>\n    </object>\n' for oid, tags in self.tags.items())
        return '<?xml version="1.0" encoding="UTF-8"?>\n<metadata>\n' + body + '</metadata>\n'

    def render(self):
        """Render the objects that are collected lazily (business objects, environment variables, project defaults), then give every
        object a content-derived versionId. The server keys object versions by (id, versionId): a re-imported snapshot whose object
        carries the versionId of an earlier snapshot is treated as unchanged and keeps behaving like the old one (verified on 26 - a
        corrected coach kept failing until its versionId changed). Unchanged objects keep their versionId across rebuilds."""
        if not getattr(self, '_rendered', False):
            self._render_bos(); self._render_envs(); self._render_defaults(); self._rendered = True
            for oid, (name, typ, xml) in list(self.objects.items()):
                m = own_version(xml)   # the object's own versionId (the manifest repeats it)
                if m:
                    h = str(uuid.uuid5(self.ns, 'content:' + oid + ':' + xml[:m.start(1)] + xml[m.end(1):]))
                    self.objects[oid] = (name, typ, xml[:m.start(1)] + h + xml[m.end(1):])
    def validate(self):
        """Cheap checks that catch the mistakes that cost an import cycle: every '/12.', '/1.', '/24.', '/61.' reference resolves to an object
        of the package, every '<dep>/' prefix is a declared dependency, inner ids (2025./2027./2055./2056./3011..3014./2054./2094./2092.)
        are unique across objects, layout item ids are unique per coach (asserted at render time), option labels are short."""
        self.render()
        errors = []; inner = {}
        local_ids = set(self.objects)
        for oid, (name, typ, xml) in self.objects.items():
            for m in re.finditer(r'(?<![\w/.-])/((?:1|12|24|61|64)\.[0-9a-f-]{36})', xml):
                if m.group(1) not in local_ids: errors.append(f'{name}: dangling local reference /{m.group(1)}')
            for m in re.finditer(r'([0-9a-f-]{36})/(?:12|24|64|72)\.', xml):
                if m.group(1) not in (self.dep_sys, self.dep_ui): errors.append(f'{name}: undeclared dependency prefix {m.group(1)}')
            declared = re.findall(r'<processParameter name="[^"]*">\s*<lastModified[^>]*>\s*<lastModifiedBy[^>]*>\s*<processParameterId>([^<]+)<', xml)   # a parameterMapping repeats the callee's parameter id legitimately
            for m in re.finditer(r'<(?:processItemId|processLinkId|processVariableId|parameterMappingId|scriptId|subProcessId|switchId|switchConditionId|exitPointId|envVarId|envVarDefaultId|coachViewConfigOptionId|coachViewBindingTypeId|coachViewInlineScriptId)>([^<]+)<', xml):
                if m.group(1) in inner and inner[m.group(1)] != oid: errors.append(f'{name}: inner id {m.group(1)} also used by {self.objects[inner[m.group(1)]][0]}')
                inner[m.group(1)] = oid
            for pid in declared:
                if pid in inner and inner[pid] != oid: errors.append(f'{name}: parameter id {pid} also declared by {self.objects[inner[pid]][0]}')
                inner[pid] = oid
            for m in re.finditer(r'<label>([^<]*)</label>', xml):
                if len(m.group(1)) > 58: errors.append(f'{name}: option label longer than 58 characters ({m.group(1)[:30]}...)')
            if 'eventON_' in xml:
                for m in re.finditer(r'<ns\d+:optionName>event[A-Z_]+</ns\d+:optionName><ns\d+:value>([^<]*)</ns\d+:value>', xml):
                    if '\\' in m.group(1): errors.append(f'{name}: event expression contains a backslash ({m.group(1)[:40]}...)')
        for m in re.finditer(r'attachedService</ns18:optionName><ns18:value>([^<]*)<', ''.join(x for _, _, x in self.objects.values())):
            if m.group(1) not in self.objects: errors.append(f'Service Call attached to unknown service {m.group(1)}')
        return errors

    def write(self, path):
        """Write the TWX (and <path>.ids.json with the ids the tests need). Raises when validate() reports errors."""
        self.render()
        errors = self.validate()
        if errors: raise ValueError('package errors:\n  ' + '\n  '.join(errors))
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\n\n')
            z.writestr('META-INF/package.xml', self.package_xml())
            z.writestr('META-INF/metadata.xml', self.metadata_xml())
            for oid, (name, typ, xml) in self.objects.items(): z.writestr(f'objects/{oid}.xml', xml)
            for p, data in self.files.items(): z.writestr(p, data)
        ids = dict(app=self.project_id, branch=self.branch_id, snapshot=self.snapshot_id, acronym=self.acronym, name=self.name,
                   cshs=self.cshs_ids, flows=self.flows, views=self.view_ids, bos=self.bos, teams=self.teams,
                   playback={n: f'/teamworks/executecf?modelID={i}&branchID={self.branch_id}' for n, i in self.cshs_ids.items()},
                   bpds=self.bpds, start_urls={n: f'/rest/bpm/wle/v1/process?action=start&bpdId={i}&branchId={self.branch_id}' for n, i in self.bpds.items()})
        idpath = re.sub(r'\.twx$', '', path) + '.ids.json'
        json.dump(ids, open(idpath, 'w'), indent=1)
        return ids

# ------------------------------------------------------------------------------------------------------ business process renderer
def render_bpd(app, name, bid, nodes, flows, lanes, inputs, variables, searchable, exposed_team, instance_name, description):
    """BPD object (25.) in the three representations the server reads: bpmn2Data (BPMN), jsonData (variables) and the legacy
    BusinessProcessDiagram block (import), plus the <bpdParameter> header blocks. Called by App.bpd() with resolved ids: type ids
    '12.x' (System Data, dependency prefix added here) or '/12.x' (business object of the app), teams likewise ('24.x' / '/24.x'),
    node y relative to the lane top. Port of the builder verified on 8.6.2 / BAW 26 (docs/TWX-AUTHORING-NOTES, "Process app authoring")."""
    S = T_STRING = TYPES['String']; WLE = 'http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process/wle'
    did = app.did; dep = lambda cid: f'{app.dep_sys}/{cid}'; now = NOW
    defs_id = did('definitions', name); defs_open = BPD_DEFS_OPEN % defs_id
    ids = {k: did('bpd', name, k) for k in ['laneSet', 'caseFolder', 'inputSet', 'outputSet', 'interface']}
    for n in nodes: ids[n['key']] = did('bpd', name, 'node', n['key'])
    for f in flows: ids[f[0]] = did('bpd', name, 'flow', f[0])
    for l in lanes: ids[l['key']] = did('bpd', name, 'lane', l['key'])
    for n, ty, dv in inputs: ids['in.' + n] = did('bpd', name, 'input', n)
    for n, ty in variables: ids['var.' + n] = did('bpd', name, 'var', n)
    for alias, var, path, ty in searchable: ids['sf.' + alias] = did('bpd', name, 'searchable', alias)
    sf_of = lambda var: [x for x in searchable if x[1] == var]
    instance_name = instance_name or f'"{name}:" + tw.system.process.instanceId'
    S = T_STRING
    def bpdid(key): u = did('bpdid', name, key).replace('-', ''); return f'bpdid:{u[:16]}:{u[16:24]}:{u[24:32]}:-{u[:4]}'
    out_flows = {n['key']: [f for f in flows if f[1] == n['key']] for n in nodes}; in_flows = {n['key']: [f for f in flows if f[2] == n['key']] for n in nodes}
    # a decision gateway evaluates its outgoing flows in order and the default matches always: conditional flows first, the default last
    for n in nodes:
        if n['kind'] == 'gateway': out_flows[n['key']] = [f for f in out_flows[n['key']] if len(f) > 4 and f[4]] + [f for f in out_flows[n['key']] if not (len(f) > 4 and f[4])]
    size = lambda n: (24, 24) if n['kind'] in ('start', 'end', 'timer', 'boundary', 'messageStart') else (32, 32) if n['kind'] in ('gateway', 'parallel') else (95, 70)
    ref = lambda ty: ty if str(ty).startswith('/') else dep(ty)          # class / team reference with the dependency prefix (System Data) or app-local
    bare = lambda ty: str(ty).lstrip('/')                                # bare id for itm. references and BPMN partitionElementRef
    cond = lambda f: f[4] if len(f) > 4 and f[4] else None
    fport = lambda f: f[5] if len(f) > 5 and f[5] else 'rightCenter'
    def default_flow(n):
        outs = out_flows[n['key']]
        if not outs: return None
        if n['kind'] == 'gateway':
            d = [f for f in outs if not cond(f)]; return d[0] if d else outs[0]
        return outs[0]
    # --------------------------------------------------------------------------------------------------------- BPMN
    def vis(n): w, h = size(n); return f'<ns13:nodeVisualInfo x="{n["x"]}" y="{n["y"]}" width="{w}" height="{h}"' + (' color="#F8F8F8"' if n['kind'] in ('start', 'end') else '') + ' />'
    def inout(n): return ''.join(f'<ns16:incoming>{ids[f[0]]}</ns16:incoming>' for f in in_flows[n['key']]) + ''.join(f'<ns16:outgoing>{ids[f[0]]}</ns16:outgoing>' for f in out_flows[n['key']])
    def default(n): return f' default="{ids[default_flow(n)[0]]}"' if out_flows[n['key']] else ''
    def defext(n): return f'<ns3:default>{ids[default_flow(n)[0]]}</ns3:default>' if out_flows[n['key']] else ''
    # user task settings: priority (Highest / High / Normal / Low / Lowest) and due offset in hours per node (defaults Normal, 1 h)
    uts_of = lambda n: f'<ns4:userTaskSettings>{subject_bpmn(n)}<ns4:activityPriority type="Priority"><ns4:priority>{n.get("priority", "Normal")}</ns4:priority></ns4:activityPriority><ns4:activityDueDate type="TimeCalculation"><ns4:dueDate unit="Hours" timeOfDay="00:00">{n.get("due_hours", 1)}</ns4:dueDate>' + '<ns4:timeZone type="TimeZone"><ns4:value>(use default)</ns4:value></ns4:timeZone></ns4:activityDueDate><ns4:activityAssignmentType>Lane</ns4:activityAssignmentType><ns4:activityWorkSchedule><ns4:timeScheduleType>0</ns4:timeScheduleType><ns4:timezoneType>0</ns4:timezoneType><ns4:holidayScheduleType>0</ns4:holidayScheduleType></ns4:activityWorkSchedule></ns4:userTaskSettings>'
    uts = '<ns4:userTaskSettings><ns4:activityPriority type="Priority"><ns4:priority>Normal</ns4:priority></ns4:activityPriority><ns4:activityDueDate type="TimeCalculation"><ns4:dueDate unit="Hours" timeOfDay="00:00">1</ns4:dueDate><ns4:timeZone type="TimeZone"><ns4:value>(use default)</ns4:value></ns4:timeZone></ns4:activityDueDate><ns4:activityAssignmentType>Lane</ns4:activityAssignmentType><ns4:activityWorkSchedule><ns4:timeScheduleType>0</ns4:timeScheduleType><ns4:timezoneType>0</ns4:timezoneType><ns4:holidayScheduleType>0</ns4:holidayScheduleType></ns4:activityWorkSchedule></ns4:userTaskSettings>'
    performers = '<ns4:activityPerformer distribution="None" teamAssignmentType="Reference" name="Lane"><ns4:teamFilterService /></ns4:activityPerformer><ns4:activityPerformer distribution="None" teamAssignmentType="Reference" name="Team"><ns4:teamFilterService /></ns4:activityPerformer><ns16:performer name="Expert" />'
    def assoc(n):
        s = ''
        for pref, expr, ty in n.get('inputs', []): s += f'<ns16:dataInputAssociation><ns16:targetRef>{pref}</ns16:targetRef><ns16:assignment><ns16:from xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns16:tFormalExpression" evaluatesToTypeRef="itm.{bare(ty)}">{esc(expr)}</ns16:from></ns16:assignment></ns16:dataInputAssociation>'
        for pref, var, ty in n.get('outputs', []): s += f'<ns16:dataOutputAssociation><ns16:sourceRef>{pref}</ns16:sourceRef><ns16:assignment><ns16:to xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns16:tFormalExpression" evaluatesToTypeRef="itm.{bare(ty)}">tw.local.{var}</ns16:to></ns16:assignment></ns16:dataOutputAssociation>'
        return s
    # timer settings: relative to the token arrival (hours= or minutes=, default 1 hour) or a custom date expression (custom='tw.local.at', fires at that date)
    def timer_parts(n):
        if n.get('custom'): return dict(dateType='Custom', custom=n['custom'], direction='AfterCustomDate', time='0', unit='Minutes')
        if 'minutes' in n: return dict(dateType='Now', custom='', direction='AfterStart', time=str(n['minutes']), unit='Minutes')
        return dict(dateType='Now', custom='', direction='AfterStart', time=str(n.get('hours', 1)), unit='Hours')
    def timer_bpmn(n):
        tp = timer_parts(n)
        return (f'<ns4:customDate>{esc(tp["custom"])}</ns4:customDate>' if tp['custom'] else '') + f'<ns4:dateType>{tp["dateType"]}</ns4:dateType><ns4:relativeDirection>{tp["direction"]}</ns4:relativeDirection><ns4:relativeTime>{tp["time"]}</ns4:relativeTime><ns4:relativeTimeResolution>{tp["unit"]}</ns4:relativeTimeResolution>'
    # user task subject / narrative templates ("<#= tw.local.x #>" placeholders), shown in the task list and the task details
    def subject_bpmn(n): return (f'<ns4:narrative>{esc(n["narrative"])}</ns4:narrative>' if n.get('narrative') else '') + (f'<ns4:subject>{esc(n["subject"])}</ns4:subject>' if n.get('subject') else '')
    def node_xml(n):
        k, i, nm = n['kind'], ids[n['key']], attr(n['name'])
        if k == 'start': return f'<ns16:startEvent name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}{defext(n)}</ns16:extensionElements>{inout(n)}</ns16:startEvent>'
        if k == 'messageStart':
            return (f'<ns16:startEvent isInterrupting="true" name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}{defext(n)}</ns16:extensionElements>{inout(n)}{assoc(n)}'
                    f'<ns4:ucaMessageEventDefinition id="{did("bpd", name, "msgDef", n["key"])}" eventImplId="{did("bpd", name, "msgImpl", n["key"])}"><ns4:attachedUCA>{n["uca"]}</ns4:attachedUCA><ns16:script /><ns4:consumeMessage>true</ns4:consumeMessage><ns4:durableSubscription>true</ns4:durableSubscription><ns4:triggerTargetInSnapshotCtx>false</ns4:triggerTargetInSnapshotCtx><ns4:bpdEventId>{did("bpd", name, "bpdEvent", n["key"])}</ns4:bpdEventId></ns4:ucaMessageEventDefinition></ns16:startEvent>')
        if k == 'gateway': return f'<ns16:exclusiveGateway{default(n)} name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}</ns16:extensionElements>{inout(n)}</ns16:exclusiveGateway>'
        if k == 'parallel': return f'<ns16:parallelGateway gatewayDirection="Unspecified" name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}</ns16:extensionElements>{inout(n)}</ns16:parallelGateway>'
        if k == 'end': return f'<ns16:endEvent name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}</ns16:extensionElements>{inout(n)}</ns16:endEvent>'
        if k == 'timer':
            return (f'<ns16:intermediateCatchEvent name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}{defext(n)}</ns16:extensionElements>{inout(n)}'
                    f'<ns16:timerEventDefinition id="{did("bpd", name, "timerDef", n["key"])}" eventImplId="{did("bpd", name, "timerImpl", n["key"])}"><ns16:extensionElements><ns4:timerEventSettings>{timer_bpmn(n)}<ns4:toleranceInterval>0</ns4:toleranceInterval><ns4:toleranceIntervalResolution>Hours</ns4:toleranceIntervalResolution><ns4:useCalendar>false</ns4:useCalendar></ns4:timerEventSettings></ns16:extensionElements></ns16:timerEventDefinition></ns16:intermediateCatchEvent>')
        if k == 'boundary':
            return (f'<ns16:boundaryEvent cancelActivity="{"true" if n.get("interrupting") else "false"}" attachedToRef="{ids[n["attach"]]}" parallelMultiple="false" name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}{defext(n)}</ns16:extensionElements>{inout(n)}'
                    f'<ns16:timerEventDefinition id="{did("bpd", name, "timerDef", n["key"])}" eventImplId="{did("bpd", name, "timerImpl", n["key"])}"><ns16:extensionElements><ns4:timerEventSettings>{timer_bpmn(n)}<ns4:toleranceInterval>0</ns4:toleranceInterval><ns4:toleranceIntervalResolution>Hours</ns4:toleranceIntervalResolution><ns4:useCalendar>false</ns4:useCalendar></ns4:timerEventSettings></ns16:extensionElements></ns16:timerEventDefinition></ns16:boundaryEvent>')
        if k == 'script': return f'<ns16:scriptTask scriptFormat="text/x-javascript"{default(n)} name="{nm}" id="{i}"><ns16:extensionElements>{vis(n)}</ns16:extensionElements>{inout(n)}<ns16:script>{esc(n["script"])}</ns16:script></ns16:scriptTask>'
        if k == 'service':
            return (f'<ns16:callActivity calledElement="{n["callee"]}"{default(n)} name="{nm}" id="{i}"><ns16:extensionElements><ns4:deleteTaskOnCompletion>true</ns4:deleteTaskOnCompletion>{vis(n)}{uts}<ns4:activityType>ServiceTask</ns4:activityType><ns4:activityExtension conditional="false"><ns4:conditionScript /></ns4:activityExtension></ns16:extensionElements>{inout(n)}{assoc(n)}{performers}</ns16:callActivity>')
        if k == 'user':
            return (f'<ns16:callActivity calledElement="{n["callee"]}" isForCompensation="false" startQuantity="1" completionQuantity="1"{default(n)} name="{nm}" id="{i}"><ns16:extensionElements><ns4:activityExtension conditional="false" transactionalBehavior="NotSet"><ns4:conditionScript /></ns4:activityExtension>{vis(n)}{uts_of(n)}<ns4:activityType>{"InlineUserTask" if n.get("inline") else "UserTask"}</ns4:activityType></ns16:extensionElements>{inout(n)}{assoc(n)}{performers}</ns16:callActivity>')
        raise ValueError(k)
    def flow_xml(f): return (f'<ns16:sequenceFlow sourceRef="{ids[f[1]]}" targetRef="{ids[f[2]]}" name="{attr(f[3])}" id="{ids[f[0]]}"><ns16:extensionElements><ns3:sequenceFlowImplementation sboSyncEnabled="true" fireValidation="Never" /><ns13:linkVisualInfo><ns13:sourcePortLocation>{fport(f)}</ns13:sourcePortLocation><ns13:targetPortLocation>leftCenter</ns13:targetPortLocation><ns13:showLabel>false</ns13:showLabel><ns13:showCoachControlLabel>false</ns13:showCoachControlLabel><ns13:labelPosition>0.0</ns13:labelPosition><ns13:saveExecutionContext>true</ns13:saveExecutionContext></ns13:linkVisualInfo><ns3:happySequence>true</ns3:happySequence></ns16:extensionElements>' + (f'<ns16:conditionExpression xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns16:tFormalExpression">{esc(cond(f))}</ns16:conditionExpression>' if cond(f) else '') + '</ns16:sequenceFlow>')
    lane_xml = ''.join(f'<ns16:lane name="{attr(l["name"])}" partitionElementRef="{bare(l["team"])}" id="{ids[l["key"]]}" ns4:isSystemLane="{"true" if l.get("system") else "false"}"><ns16:extensionElements><ns13:nodeVisualInfo x="0" y="{l["y"]}" width="3000" height="{l["height"]}" color="#F8F8F8" /></ns16:extensionElements>' + ''.join(f'<ns16:flowNodeRef>{ids[n["key"]]}</ns16:flowNodeRef>' for n in nodes if n['lane'] == l['key']) + '</ns16:lane>' for l in lanes)
    user_callees = sorted({n['callee'] for n in nodes if n['kind'] == 'user' and n.get('inline')})   # only inline tasks are declared as globalUserTask in the BPD; a library human service is just called (Standard Hiring Sample shape)
    bpmn = (defs_open + f'<ns16:process name="{attr(name)}" id="{bid}" ns3:executionMode="longRunning"><ns16:documentation textFormat="text/plain" /><ns16:extensionElements>'
            f'<ns4:bpdExtension instanceName="{attr(instance_name)}" dueDateEnabled="false" atRiskCalcEnabled="false" enableTracking="false" allowProjectedPathManagement="false" optimizeExecForLatency="false" sBOSyncEnabled="true" allowContentOperations="false" autoTrackingEnabled="false" autoTrackingName="at{now}">'
            f'<ns4:dueDateSettings type="TimeCalculation"><ns4:dueDate unit="Hours" timeOfDay="00:00">8</ns4:dueDate></ns4:dueDateSettings><ns4:workSchedule><ns4:timeScheduleType>0</ns4:timeScheduleType><ns4:timezoneType>0</ns4:timezoneType><ns4:holidayScheduleType>0</ns4:holidayScheduleType></ns4:workSchedule></ns4:bpdExtension>'
            f'<ns2:caseExtension><ns2:caseFolder id="{ids["caseFolder"]}" /></ns2:caseExtension><ns2:isConvergedProcess>true</ns2:isConvergedProcess></ns16:extensionElements><ns16:ioSpecification>'
            + ''.join(f'<ns16:dataInput name="{n}" itemSubjectRef="itm.{bare(ty)}" isCollection="false" id="2007.{ids["in." + n]}"><ns16:extensionElements><ns3:defaultValue useDefault="true">{esc(dv)}</ns3:defaultValue></ns16:extensionElements></ns16:dataInput>' for n, ty, dv in inputs)
            + f'<ns16:inputSet id="_{ids["inputSet"]}" /><ns16:outputSet id="_{ids["outputSet"]}" /></ns16:ioSpecification><ns16:laneSet id="{ids["laneSet"]}">{lane_xml}</ns16:laneSet>'
            + ''.join(node_xml(n) for n in nodes) + ''.join(flow_xml(f) for f in flows)
            + ''.join((f'<ns16:dataObject itemSubjectRef="itm.{bare(ty)}" isCollection="false" name="{n}" id="{ids["var." + n]}"><ns16:extensionElements>' + ''.join(f'<ns4:searchableField id="{bpdid("sf." + alias)}" alias="{attr(alias)}" path="{attr(path)}" type="{bare(sty)}" />' for alias, var, path, sty in sf_of(n)) + '</ns16:extensionElements></ns16:dataObject>') if sf_of(n) else f'<ns16:dataObject itemSubjectRef="itm.{bare(ty)}" isCollection="false" name="{n}" id="{ids["var." + n]}" />' for n, ty in variables)
            + (f'<ns16:resourceRole name="participantRef"><ns16:resourceRef>{bare(exposed_team)}</ns16:resourceRef></ns16:resourceRole>' if exposed_team else '<ns16:resourceRole name="participantRef" />')
            + '<ns16:resourceRole name="businessDataParticipantRef" /><ns16:resourceRole name="perfMetricParticipantRef" /><ns16:resourceRole name="ownerTeamParticipantRef" />'
            f'</ns16:process><ns16:interface name="{attr(name)}Interface" id="_{ids["interface"]}" />'
            + ''.join(f'<ns16:globalUserTask implementation="##unspecified" name="{c}" id="{c}"><ns16:ioSpecification><ns16:inputSet id="{did("bpd", name, "gut-in", c)}" /><ns16:outputSet id="{did("bpd", name, "gut-out", c)}" /></ns16:ioSpecification></ns16:globalUserTask>' for c in user_callees)
            + '</ns16:definitions>')
    # --------------------------------------------------------------------------------------------------------- JSON
    def nvi(n): w, h = size(n); d = {"width": w, "x": n['x'], "y": n['y'], "declaredType": "TNodeVisualInfo", "height": h}; return ({**d, "color": "#F8F8F8"} if n['kind'] in ('start', 'end') else d)
    def jio(n):
        d = {}
        if in_flows[n['key']]: d['incoming'] = [ids[f[0]] for f in in_flows[n['key']]]
        if out_flows[n['key']]: d['outgoing'] = [ids[f[0]] for f in out_flows[n['key']]]
        return d
    def jdefault(n): return {"default": ids[default_flow(n)[0]]} if out_flows[n['key']] else {}
    def jassoc(n): return {"dataInputAssociation": [{"targetRef": pref, "assignment": [{"from": {"evaluatesToTypeRef": "itm." + bare(ty), "declaredType": "TFormalExpression", "content": [expr]}}]} for pref, expr, ty in n.get('inputs', [])],
                           "dataOutputAssociation": [{"assignment": [{"to": {"evaluatesToTypeRef": "itm." + bare(ty), "declaredType": "TFormalExpression", "content": ["tw.local." + var]}}], "sourceRef": [pref]} for pref, var, ty in n.get('outputs', [])]}
    juts = {"activityAssignmentType": "Lane", "activityWorkSchedule": {"timezoneType": 0, "timeScheduleType": 0, "holidayScheduleType": 0}, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TUserTaskSettings", "activityPriority": {"type": "Priority", "priority": "Normal"}, "activityDueDate": {"dueDate": {"unit": "Hours", "value": "1", "timeOfDay": "00:00"}, "timeZone": {"type": "TimeZone", "value": "(use default)"}, "type": "TimeCalculation"}}
    juts_of = lambda n: {**juts, **({"narrative": n['narrative']} if n.get('narrative') else {}), **({"subject": n['subject']} if n.get('subject') else {}), "activityPriority": {"type": "Priority", "priority": n.get('priority', 'Normal')}, "activityDueDate": {**juts["activityDueDate"], "dueDate": {"unit": "Hours", "value": str(n.get('due_hours', 1)), "timeOfDay": "00:00"}}}
    jperf = [{"teamAssignmentType": "Reference", "name": "Lane", "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TActivityPerformer", "distribution": "None", "teamFilterService": {}}, {"teamAssignmentType": "Reference", "name": "Team", "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TActivityPerformer", "distribution": "None", "teamFilterService": {}}, {"name": "Expert", "declaredType": "performer"}]
    def node_json(n):
        k, i, nm = n['kind'], ids[n['key']], n['name']; base = {**jio(n), "name": nm, "id": i}
        if k == 'start': return {**base, "parallelMultiple": False, "isInterrupting": True, "extensionElements": {**({"default": [ids[default_flow(n)[0]]]} if out_flows[n['key']] else {}), "nodeVisualInfo": [nvi(n)]}, "declaredType": "startEvent"}
        if k == 'messageStart':
            return {**base, "parallelMultiple": False, "isInterrupting": True, "extensionElements": {**({"default": [ids[default_flow(n)[0]]]} if out_flows[n['key']] else {}), "nodeVisualInfo": [nvi(n)]}, "dataOutputAssociation": jassoc(n)["dataOutputAssociation"],
                    "eventDefinition": [{"declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TUCAMessageEventDefinition", "id": did("bpd", name, "msgDef", n["key"]), "eventImplId": did("bpd", name, "msgImpl", n["key"]), "attachedUCA": n["uca"], "script": {}, "consumeMessage": True, "durableSubscription": True, "triggerTargetInSnapshotCtx": False, "bpdEventId": did("bpd", name, "bpdEvent", n["key"])}], "declaredType": "startEvent"}
        if k == 'gateway': return {**base, **jdefault(n), "gatewayDirection": "Unspecified", "extensionElements": {"nodeVisualInfo": [nvi(n)]}, "declaredType": "exclusiveGateway"}
        if k == 'parallel': return {**base, "gatewayDirection": "Unspecified", "extensionElements": {"nodeVisualInfo": [nvi(n)]}, "declaredType": "parallelGateway"}
        if k == 'end': return {**base, "extensionElements": {"nodeVisualInfo": [nvi(n)]}, "declaredType": "endEvent"}
        if k == 'timer': return {**base, "parallelMultiple": False, "eventDefinition": [{"extensionElements": {"timerEventSettings": [{**({"customDate": timer_parts(n)['custom']} if timer_parts(n)['custom'] else {}), "relativeTime": timer_parts(n)['time'], "relativeTimeResolution": timer_parts(n)['unit'], "dateType": timer_parts(n)['dateType'], "toleranceInterval": "0", "useCalendar": False, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TTimerEventSettings", "toleranceIntervalResolution": "Hours", "relativeDirection": timer_parts(n)['direction']}]}, "declaredType": "timerEventDefinition", "id": did("bpd", name, "timerDef", n["key"]), "otherAttributes": {"eventImplId": did("bpd", name, "timerImpl", n["key"])}}], "extensionElements": {**({"default": [ids[out_flows[n['key']][0][0]]]} if out_flows[n['key']] else {}), "nodeVisualInfo": [nvi(n)]}, "declaredType": "intermediateCatchEvent"}
        if k == 'boundary':
            return {**base, "cancelActivity": bool(n.get('interrupting')), "attachedToRef": ids[n['attach']], "parallelMultiple": False, "eventDefinition": [{"extensionElements": {"timerEventSettings": [{**({"customDate": timer_parts(n)['custom']} if timer_parts(n)['custom'] else {}), "relativeTime": timer_parts(n)['time'], "relativeTimeResolution": timer_parts(n)['unit'], "dateType": timer_parts(n)['dateType'], "toleranceInterval": "0", "useCalendar": False, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TTimerEventSettings", "toleranceIntervalResolution": "Hours", "relativeDirection": timer_parts(n)['direction']}]}, "declaredType": "timerEventDefinition", "id": did("bpd", name, "timerDef", n["key"]), "otherAttributes": {"eventImplId": did("bpd", name, "timerImpl", n["key"])}}], "extensionElements": {**({"default": [ids[out_flows[n['key']][0][0]]]} if out_flows[n['key']] else {}), "nodeVisualInfo": [nvi(n)]}, "declaredType": "boundaryEvent"}
        if k == 'script': return {**base, "startQuantity": 1, **jdefault(n), "extensionElements": {"nodeVisualInfo": [nvi(n)]}, "isForCompensation": False, "completionQuantity": 1, "declaredType": "scriptTask", "scriptFormat": "text/x-javascript", "script": {"content": [n['script']]}}
        if k == 'service':
            return {**base, "extensionElements": {"activityExtension": [{"conditionScript": "", "conditional": False, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TActivityExtension"}], "deleteTaskOnCompletion": [True], "nodeVisualInfo": [nvi(n)], "userTaskSettings": [juts], "activityType": ["ServiceTask"]}, "declaredType": "callActivity", "startQuantity": 1, "resourceRole": [{**p, **({} if 'teamAssignmentType' not in p else {})} for p in jperf], **jdefault(n),
                    "dataInputAssociation": jassoc(n)["dataInputAssociation"], "dataOutputAssociation": jassoc(n)["dataOutputAssociation"],
                    "isForCompensation": False, "completionQuantity": 1, "calledElement": n['callee']}
        if k == 'user':
            return {**base, "startQuantity": 1, "resourceRole": jperf, **jdefault(n), "extensionElements": {"activityExtension": [{"conditionScript": "", "conditional": False, "transactionalBehavior": "NotSet", "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TActivityExtension"}], "nodeVisualInfo": [nvi(n)], "userTaskSettings": [juts_of(n)], "activityType": ["InlineUserTask" if n.get("inline") else "UserTask"]}, "isForCompensation": False, "completionQuantity": 1, "declaredType": "callActivity", "calledElement": n['callee'], **jassoc(n)}
    fe = [node_json(n) for n in nodes]
    for f in flows: fe.append({"targetRef": ids[f[2]], "extensionElements": {"sequenceFlowImplementation": [{"fireValidation": "Never", "sboSyncEnabled": True, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmext.TSequenceFlowImplementation"}], "linkVisualInfo": [{"sourcePortLocation": fport(f), "showCoachControlLabel": False, "labelPosition": 0.0, "targetPortLocation": "leftCenter", "declaredType": "TLinkVisualInfo", "saveExecutionContext": True, "showLabel": False}], "happySequence": [True]}, "name": f[3], "declaredType": "sequenceFlow", "id": ids[f[0]], "sourceRef": ids[f[1]], **({"conditionExpression": {"declaredType": "TFormalExpression", "content": [cond(f)]}} if cond(f) else {})})
    for n, ty in variables: fe.append({"itemSubjectRef": "itm." + bare(ty), "name": n, "isCollection": False, "declaredType": "dataObject", "id": ids['var.' + n], **({"extensionElements": {"searchableField": [{"alias": alias, "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TSearchableField", "path": path, "type": bare(sty), "id": bpdid("sf." + alias)} for alias, var, path, sty in sf_of(n)]}} if sf_of(n) else {})})
    proc = {"flowElement": fe,
            "laneSet": [{"id": ids['laneSet'], "lane": [{"flowNodeRef": [ids[n['key']] for n in nodes if n['lane'] == l['key']], "extensionElements": {"nodeVisualInfo": [{"color": "#F8F8F8", "width": 3000, "x": 0, "y": l['y'], "declaredType": "TNodeVisualInfo", "height": l['height']}]}, "name": l['name'], "partitionElementRef": bare(l['team']), "declaredType": "lane", "id": ids[l['key']], "otherAttributes": {"{" + WLE + "}isSystemLane": "true" if l.get('system') else "false"}} for l in lanes]}],
            "resourceRole": [({"resourceRef": bare(exposed_team), "name": "participantRef", "declaredType": "resourceRole"} if exposed_team else {"name": "participantRef", "declaredType": "resourceRole"}), {"name": "businessDataParticipantRef", "declaredType": "resourceRole"}, {"name": "perfMetricParticipantRef", "declaredType": "resourceRole"}, {"name": "ownerTeamParticipantRef", "declaredType": "resourceRole"}],
            "isClosed": False,
            "extensionElements": {"bpdExtension": [{"allowContentOperations": False, "enableTracking": False, "workSchedule": {"timezoneType": 0, "timeScheduleType": 0, "holidayScheduleType": 0}, "instanceName": instance_name, "dueDateSettings": {"dueDate": {"unit": "Hours", "value": "8", "timeOfDay": "00:00"}, "type": "TimeCalculation"}, "autoTrackingName": f"at{now}", "declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmwleext.TBPDExtension", "optimizeExecForLatency": False, "dueDateEnabled": False, "atRiskCalcEnabled": False, "allowProjectedPathManagement": False, "autoTrackingEnabled": False, "sboSyncEnabled": True}],
                                  "caseExtension": [{"declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmcaseext.TCaseExtension", "caseFolder": {"allowSubfoldersCreation": False, "allowLocalDoc": False, "id": ids['caseFolder'], "allowExternalFolder": False, "allowExternalDoc": False}}], "isConvergedProcess": [True]},
            "documentation": [{"textFormat": "text/plain"}], "name": name, "declaredType": "process", "id": bid, "processType": "None", "otherAttributes": {"{http://www.ibm.com/xmlns/prod/bpm/bpmn/ext/process}executionMode": "longRunning"},
            "ioSpecification": {"inputSet": [{"id": "_" + ids['inputSet']}], "outputSet": [{"id": "_" + ids['outputSet']}],
                                "dataInput": [{"extensionElements": {"defaultValue": [{"declaredType": "com.ibm.bpmsdk.model.bpmn20.ibmext.TDefaultValue", "useDefault": True, "value": dv}]}, "itemSubjectRef": "itm." + bare(ty), "name": n, "isCollection": False, "id": "2007." + ids['in.' + n]} for n, ty, dv in inputs]}}
    roots = [proc, {"name": name + "Interface", "declaredType": "interface", "id": "_" + ids['interface']}] + [{"implementation": "##unspecified", "name": c, "declaredType": "globalUserTask", "id": c, "ioSpecification": {"inputSet": [{"id": did("bpd", name, "gut-in", c)}], "outputSet": [{"id": did("bpd", name, "gut-out", c)}]}} for c in user_callees]
    jdata = {"rootElement": roots, "targetNamespace": "", "typeLanguage": "http://www.w3.org/2001/XMLSchema", "expressionLanguage": "http://www.ibm.com/xmlns/prod/bpm/expression-lang/javascript", "id": defs_id}
    # -------------------------------------------------------------------------------------------------------- legacy
    def port(kind, f, key): return f'<{kind}Port id="{bpdid(key)}"><positionId>{"leftCenter" if kind == "input" else fport(f)}</positionId>{"<input>true</input>" if kind == "input" else ""}<flow ref="{ids[f[0]]}" /></{kind}Port>'
    def ports(n): return ''.join(port('input', f, 'p.' + n['key'] + '.in.' + f[0]) for f in in_flows[n['key']]) + ''.join(port('output', f, 'p.' + n['key'] + '.out.' + f[0]) for f in out_flows[n['key']])
    def event(n, event_type, extra=''): return f'<flowObject id="{ids[n["key"]]}" componentType="Event"><name>{esc(n["name"])}</name><documentation></documentation><position><location x="{n["x"]}" y="{n["y"]}" /></position><dropIconUrl>0</dropIconUrl><colorInput>#F8F8F8</colorInput><component><nameVisible>true</nameVisible><eventType>{event_type}</eventType><cancelActivity>true</cancelActivity><repeatable>false</repeatable><doCloseTask>true</doCloseTask>{extra}</component>{ports(n)}</flowObject>'
    common = '<loopType>0</loopType><loopMaximum>1</loopMaximum><startQuantity>1</startQuantity><isAutoflowable>false</isAutoflowable><MIOrdering>1</MIOrdering><MIFlowCondition>0</MIFlowCondition><cancelRemainingInstances>false</cancelRemainingInstances><metricSettings itemType="4" />'
    tail_flags = '<activityOptionType>REQUIRED</activityOptionType><activityExecutionType>NONE</activityExecutionType><activityExecutionTypePreviousValue>AUTOMATIC</activityExecutionTypePreviousValue><isHidden>false</isHidden><isRepeatable>false</isRepeatable><transactionalBehavior>0</transactionalBehavior><isRobotTask>false</isRobotTask>'
    sched = '<dueDateType>1</dueDateType><dueDateTime>1</dueDateTime><dueDateTimeResolution>1</dueDateTimeResolution><dueDateTimeTOD>00:00</dueDateTimeTOD><priorityType>0</priorityType><priority>30.30</priority><forceSend>true</forceSend>'
    # legacy task schedule per node: priority code (<value>.<value>: 10 Highest ... 50 Lowest) and due offset in hours (resolution 1 = hours)
    PRIORITY_CODE = {'Normal': '30.30'}   # only the default is known to import ('20.20' fails with "Invalid UUID string '20'" in BPDTaskActivityImplAG.priorityFromXML); other values pending the Hiring Sample export
    sched_of = lambda n: f'<dueDateType>1</dueDateType><dueDateTime>{n.get("due_hours", 1)}</dueDateTime><dueDateTimeResolution>1</dueDateTimeResolution><dueDateTimeTOD>00:00</dueDateTimeTOD><priorityType>0</priorityType><priority>{PRIORITY_CODE.get(n.get("priority", "Normal"), "30.30")}</priority>' + (f'<subject>{esc(n["subject"])}</subject>' if n.get('subject') else '') + (f'<narrative>{esc(n["narrative"])}</narrative>' if n.get('narrative') else '') + '<forceSend>true</forceSend>'
    sched2 = '<timeSchedule>(use default)</timeSchedule><timeScheduleType>0</timeScheduleType><timeZone>(use default)</timeZone><timeZoneType>0</timeZoneType><holidaySchedule>(use default)</holidaySchedule><holidayScheduleType>0</holidayScheduleType>'
    def activity(n, body): return f'<flowObject id="{ids[n["key"]]}" componentType="Activity"><name>{esc(n["name"])}</name><documentation></documentation><position><location x="{n["x"]}" y="{n["y"]}" /></position><dropIconUrl>0</dropIconUrl><colorInput>#A5B7CD</colorInput><component>{body}</component>{ports(n)}{attached(n)}</flowObject>'
    def timer_action(n):
        tp = timer_parts(n)   # legacy codes: dateType 0 = now, 2 = custom date; resolution 0 = minutes, 1 = hours
        return f'<EventAction id="{did("bpd", name, "timerDef", n["key"])}"><actionType>2</actionType><actionSubType>0</actionSubType><EventActionImplementation id="{did("bpd", name, "timerImpl", n["key"])}"><dateType>{2 if tp["custom"] else 0}</dateType>' + (f'<customDate>{esc(tp["custom"])}</customDate>' if tp['custom'] else '') + f'<relativeDirection>1</relativeDirection><relativeTime>{tp["time"]}</relativeTime><relativeTimeResolution>{0 if tp["unit"] == "Minutes" else 1}</relativeTimeResolution><toleranceInterval>0</toleranceInterval><toleranceIntervalResolution>1</toleranceIntervalResolution><UseCalendar>false</UseCalendar></EventActionImplementation></EventAction>'
    def attached(n):   # boundary timers of an activity: <attachedEvent> children of its flowObject (legacy format of the Process Designer)
        out = ''
        for b in [m for m in nodes if m['kind'] == 'boundary' and m['attach'] == n['key']]:
            flag = 'true' if b.get('interrupting') else 'false'
            out += (f'<attachedEvent id="{ids[b["key"]]}" componentType="Event"><name>{esc(b["name"])}</name><documentation></documentation><position><location x="0" y="0" /></position><positionId>bottomCenter</positionId><dropIconUrl>0</dropIconUrl><colorInput>Color</colorInput>'
                    f'<component><nameVisible>true</nameVisible><eventType>3</eventType><cancelActivity>{flag}</cancelActivity><repeatable>false</repeatable><doCloseTask>{flag}</doCloseTask>{timer_action(b)}</component>'
                    + ''.join(f'<outputPort id="{bpdid("p." + b["key"] + ".out." + f[0])}"><positionId>bottomCenter</positionId><flow ref="{ids[f[0]]}" /></outputPort>' for f in out_flows[b['key']]) + '</attachedEvent>')
        return out
    def lane_team(n): return [l for l in lanes if l['key'] == n['lane']][0]['team']
    def gateway(n, gateway_type=1): return f'<flowObject id="{ids[n["key"]]}" componentType="Gateway"><name>{esc(n["name"])}</name><documentation></documentation><position><location x="{n["x"]}" y="{n["y"]}" /></position><dropIconUrl>0</dropIconUrl><colorInput>#A5B7CD</colorInput><component><nameVisible>true</nameVisible><gatewayType>{gateway_type}</gatewayType><splitJoinType>0</splitJoinType></component>{ports(n)}</flowObject>'   # 1 = exclusive (decision), 5 = parallel (split)
    def message_action(n):
        outs = n.get('outputs', []); ev = did("bpd", name, "bpdEvent", n["key"]); impl = did("bpd", name, "msgImpl", n["key"]); corr = outs[0][0] if outs else ''
        maps = ''.join(f'<parameterMapping name="{var}"><lastModified isNull="true" /><lastModifiedBy isNull="true" /><parameterMappingId>2054.{did("bpd", name, "msgmap", n["key"], var)}</parameterMappingId><processParameterId>{pref}</processParameterId><parameterMappingParentId>2006.{ev}</parameterMappingParentId><useDefault>false</useDefault><value>tw.local.{var}</value><classRef>{ref(ty)}</classRef><isList>false</isList><isInput>false</isInput><guid>{did("guid", "msgmap", name, n["key"], var)}</guid><versionId>{did("version", "msgmap", name, n["key"], var)}</versionId><description isNull="true" /></parameterMapping>' for pref, var, ty in outs)
        return (f'<EventAction id="{did("bpd", name, "msgDef", n["key"])}"><actionType>1</actionType><actionSubType>0</actionSubType><EventActionImplementation id="{impl}"><consumeMessage>true</consumeMessage><durableSubscription>true</durableSubscription><attachedUcaId>/{n["uca"]}</attachedUcaId><bpdEventId>2006.{ev}</bpdEventId><correlationParameterId>{corr}</correlationParameterId><triggeringMechanism>0</triggeringMechanism>'
                f'<bpdEvent><bpdEventId>2006.{ev}</bpdEventId><ucaId>/{n["uca"]}</ucaId><bpdId>{bid}</bpdId><bpdFlowObjectId>{ids[n["key"]]}</bpdFlowObjectId><bpdObjectId>{impl}</bpdObjectId><eventType>0</eventType><correlationParameterId>{corr}</correlationParameterId><durableSubscription>true</durableSubscription><versionId>{did("version", "bpdEvent", name, n["key"])}</versionId><field1 isNull="true" /><field2 isNull="true" /><field3>0</field3><field4 isNull="true" /><field5>false</field5>{maps}</bpdEvent></EventActionImplementation></EventAction>')
    def io_maps(n):
        maps = ''.join(f'<inputActivityParameterMapping id="{bpdid("map." + n["key"] + "." + pref)}"><name>{pn}</name><classId>{ref(ty)}</classId><input>true</input><useDefault>false</useDefault><value>{esc(expr)}</value><parameterId>{pref}</parameterId></inputActivityParameterMapping>' for (pref, expr, ty), pn in zip(n.get('inputs', []), n.get('inputNames', [p[0] for p in n.get('inputs', [])])))
        maps += ''.join(f'<outputActivityParameterMapping id="{bpdid("map." + n["key"] + "." + pref)}"><name>{var}</name><classId>{ref(ty)}</classId><input>true</input><value>tw.local.{var}</value><parameterId>{pref}</parameterId></outputActivityParameterMapping>' for pref, var, ty in n.get('outputs', []))
        return maps
    def legacy_node(n):
        k = n['kind']
        if k == 'start': return event(n, 1)
        if k == 'messageStart': return event(n, 1, message_action(n))
        if k == 'gateway': return gateway(n)
        if k == 'parallel': return gateway(n, 5)
        if k == 'end': return event(n, 2)
        if k == 'boundary': return ''   # rendered inside its activity (attached())
        if k == 'timer':
            tp = timer_parts(n)   # legacy codes: dateType 0 = now, 2 = custom date; resolution 0 = minutes, 1 = hours
            return event(n, 3, f'<EventAction id="{did("bpd", name, "timerDef", n["key"])}"><actionType>2</actionType><actionSubType>0</actionSubType><EventActionImplementation id="{did("bpd", name, "timerImpl", n["key"])}"><dateType>{2 if tp["custom"] else 0}</dateType>' + (f'<customDate>{esc(tp["custom"])}</customDate>' if tp['custom'] else '') + f'<relativeDirection>1</relativeDirection><relativeTime>{tp["time"]}</relativeTime><relativeTimeResolution>{0 if tp["unit"] == "Minutes" else 1}</relativeTimeResolution><toleranceInterval>0</toleranceInterval><toleranceIntervalResolution>1</toleranceIntervalResolution><UseCalendar>false</UseCalendar></EventActionImplementation></EventAction>')
        if k == 'script': return activity(n, common + '<implementationType>3</implementationType><isConditional>false</isConditional><bpmnTaskType>4</bpmnTaskType>' + tail_flags + f'<implementation><script>{esc(n["script"])}</script></implementation>')
        if k == 'service':
            maps = io_maps(n)
            return activity(n, common + '<implementationType>4</implementationType><isConditional>false</isConditional><conditionScript></conditionScript><bpmnTaskType>3</bpmnTaskType>' + tail_flags + f'<implementation><attachedActivityId>/{n["callee"]}</attachedActivityId><sendToType>1</sendToType><taskRouting>0</taskRouting>{sched}<noTask>true</noTask>{sched2}{maps}<laneFilter id="{bpdid("laneFilter." + n["key"])}"><serviceType>1</serviceType><teamRef>{ref(lane_team(n))}</teamRef></laneFilter><teamFilter id="{bpdid("teamFilter." + n["key"])}"><serviceType>1</serviceType></teamFilter></implementation>')
        if k == 'user':
            return activity(n, common + '<implementationType>1</implementationType><isConditional>false</isConditional><conditionScript></conditionScript><bpmnTaskType>1</bpmnTaskType>' + tail_flags + f'<implementation><attachedActivityId>/{n["callee"]}</attachedActivityId><sendToType>1</sendToType><taskRouting>0</taskRouting>{sched_of(n)}{sched2}{io_maps(n)}<laneFilter id="{bpdid("laneFilter." + n["key"])}"><serviceType>1</serviceType><teamRef>{ref(lane_team(n))}</teamRef></laneFilter><teamFilter id="{bpdid("teamFilter." + n["key"])}"><serviceType>1</serviceType></teamFilter></implementation>')
        raise ValueError(k)
    legacy_flows = ''.join(f'<flow id="{ids[f[0]]}" connectionType="SequenceFlow"><name>{esc(f[3])}</name><documentation></documentation><nameVisible>false</nameVisible><metricSettings itemType="32" /><connection><lineType>0</lineType>' + (f'<condition id="{bpdid("cond." + f[0])}"><expression>{esc(cond(f))}</expression></condition>' if cond(f) else f'<condition id="{bpdid("cond." + f[0])}" />') + '</connection></flow>' for f in flows)
    office = BPD_OFFICE
    lanes_xml = ''.join(f'<lane id="{ids[l["key"]]}"><name>{esc(l["name"])}</name><height>{l["height"]}</height><laneColor>0</laneColor><systemLane>{"true" if l.get("system") else "false"}</systemLane><attachedParticipant>{ref(l["team"])}</attachedParticipant>' + ''.join(legacy_node(n) for n in nodes if n['lane'] == l['key']) + '</lane>' for l in lanes)
    pool_h = sum(l['height'] for l in lanes)
    legacy = (f'<BusinessProcessDiagram id="{bpdid("diagram")}"><metadata><entry><key>SAP_META.SHOULDRECOVER</key><value>no</value></entry></metadata><name>{esc(name)}</name><documentation></documentation><name>{esc(name)}</name><dimension><size w="600" h="150" /></dimension><author>celladmin</author>'
              f'<isTrackingEnabled>false</isTrackingEnabled><isCriticalPathEnabled>false</isCriticalPathEnabled><isSpcEnabled>false</isSpcEnabled><isDueDateEnabled>false</isDueDateEnabled><isAtRiskCalcEnabled>false</isAtRiskCalcEnabled><creationDate>{now}</creationDate><modificationDate>{now}</modificationDate>'
              + (f'<participantRef>{ref(exposed_team)}</participantRef>' if exposed_team else '') + f'<metricSettings itemType="2" /><instanceNameExpression>{esc(instance_name)}</instanceNameExpression><dueDateType>1</dueDateType><dueDateTime>8</dueDateTime><dueDateTimeResolution>1</dueDateTimeResolution><dueDateTimeTOD>00:00</dueDateTimeTOD>'
              + office + '<timeScheduleType>0</timeScheduleType><holidayScheduleType>0</holidayScheduleType><timezoneType>0</timezoneType><executionProfile>default</executionProfile><isSBOSyncEnabled>true</isSBOSyncEnabled><allowContentOperations>false</allowContentOperations><isLegacyCaseMigrated>false</isLegacyCaseMigrated><hasCaseObjectParams>false</hasCaseObjectParams>'
              f'<defaultPool><BpmnObjectId id="{ids["laneSet"]}" /></defaultPool><defaultInstanceUI id="{bpdid("defaultInstanceUI")}" /><ownerTeamInstanceUI id="{bpdid("ownerTeamInstanceUI")}" />'
              f'<simulationScenario id="{bpdid("simulation")}"><name>Default</name><simNumInstances>100</simNumInstances><simMinutesBetween>30</simMinutesBetween><maxInstances>100</maxInstances><useMaxInstances>true</useMaxInstances><continueFromReal>false</continueFromReal><useParticipantCalendars>false</useParticipantCalendars><useDuration>false</useDuration><duration>86400</duration><startTime>{now}</startTime></simulationScenario>'
              + legacy_flows + f'<pool id="{ids["laneSet"]}"><name>Pool</name><documentation></documentation><restrictedName>at{now}</restrictedName><dimension><size w="3000" h="{pool_h}" /></dimension><autoTrackingEnabled>false</autoTrackingEnabled>' + lanes_xml
              + ''.join(f'<inputParameter id="{ids["in." + n]}"><bpdParameterId>2007.{ids["in." + n]}</bpdParameterId><isProcessInstanceCorrelator>false</isProcessInstanceCorrelator></inputParameter>' for n, ty, dv in inputs)
              + ''.join(f'<privateVariable id="{ids["var." + n]}"><name>{n}</name><description></description><classId>{ref(ty)}</classId><arrayOf>false</arrayOf><hasDefault>false</hasDefault><visibleInSearch>{"true" if sf_of(n) else "false"}</visibleInSearch><isProcessInstanceCorrelator>false</isProcessInstanceCorrelator><isSharedContext>false</isSharedContext></privateVariable>' for n, ty in variables)
              + ''.join(f'<searchableField id="{bpdid("sf." + alias)}"><name>{esc(alias)}</name><type>2</type><expression id="{bpdid("sfx." + alias)}"><expression>tw.local.{var}{path}</expression></expression></searchableField>' for alias, var, path, sty in searchable)
              + f'</pool><extension id="{bpdid("caseExtension")}" type="CASE"><caseFolder id="{ids["caseFolder"]}"><allowLocalDoc>false</allowLocalDoc><allowExternalDoc>false</allowExternalDoc><allowSubfoldersCreation>false</allowSubfoldersCreation><allowExternalFolder>false</allowExternalFolder></caseFolder></extension></BusinessProcessDiagram>')
    params = ''.join(f'''        <bpdParameter name="{n}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <bpdParameterId>2007.{ids["in." + n]}</bpdParameterId>
            <bpdId>{bid}</bpdId>
            <parameterType>1</parameterType>
            <isArrayOf>false</isArrayOf>
            <classId>{ref(ty)}</classId>
            <seq>{i}</seq>
            <documentation isNull="true" />
            <hasDefault>true</hasDefault>
            <defaultValue>{esc(dv)}</defaultValue>
            <isReadOnly>false</isReadOnly>
            <guid>{did('guid', 'bpdparam', name, n)}</guid>
            <versionId>{did('version', 'bpdparam', name, n)}</versionId>
            <field1 isNull="true" />
            <field2 isNull="true" />
            <field3>0</field3>
            <field4 isNull="true" />
            <field5>false</field5>
        </bpdParameter>
''' for i, (n, ty, dv) in enumerate(inputs))
    hdr = (f'<?xml version="1.0" encoding="UTF-8"?>\n<teamworks>\n    <bpd id="{bid}" name="{attr(name)}">\n' + params
           + f'        <lastModified>{now}</lastModified>\n        <lastModifiedBy>celladmin</lastModifiedBy>\n        <bpdId>{bid}</bpdId>\n        <isTrackingEnabled>true</isTrackingEnabled>\n        <isSpcEnabled>false</isSpcEnabled>\n        <restrictedName isNull="true" />\n        <isCriticalPathEnabled>false</isCriticalPathEnabled>\n'
           + (f'        <participantRef>{ref(exposed_team)}</participantRef>\n' if exposed_team else '        <participantRef isNull="true" />\n')
           + '        <businessDataParticipantRef isNull="true" />\n        <perfMetricParticipantRef isNull="true" />\n        <ownerTeamParticipantRef isNull="true" />\n        <timeScheduleType isNull="true" />\n        <timeScheduleName isNull="true" />\n        <timeScheduleExpression isNull="true" />\n        <holidayScheduleType isNull="true" />\n        <holidayScheduleName isNull="true" />\n        <holidayScheduleExpression isNull="true" />\n        <timezoneType isNull="true" />\n        <timezone isNull="true" />\n        <timezoneExpression isNull="true" />\n        <internalName isNull="true" />\n'
           + (f'        <description>{esc(description)}</description>\n' if description else '        <description isNull="true" />\n')
           + '        <type>1</type>\n        <rootBpdId isNull="true" />\n        <parentBpdId isNull="true" />\n        <parentFlowObjectId isNull="true" />\n        <xmlData isNull="true" />\n        ')
    tail = ('\n        <dependencySummary isNull="true" />\n        <jsonData>' + esc(json.dumps(jdata)) + '</jsonData>\n        <migrationData isNull="true" />\n        <rwfData isNull="true" />\n        <rwfStatus isNull="true" />\n        <templateId isNull="true" />\n        <externalId isNull="true" />\n'
            f'        <guid>{did("guid", "bpd", name)}</guid>\n        <versionId>{did("version", "bpd", name)}</versionId>\n        <field1 isNull="true" />\n        <field2 isNull="true" />\n        <field3>0</field3>\n        <field4 isNull="true" />\n        <field5>false</field5>\n        <clobField1 isNull="true" />\n        <blobField1 isNull="true" />\n        '
            + legacy + '\n    </bpd>\n</teamworks>\n')
    return hdr + '<bpmn2Data>' + esc(bpmn) + '</bpmn2Data>' + tail

# ------------------------------------------------------------------------------------------------------ service flow renderer
def linear(app, steps):
    """Linear chain Start -> step 1 -> ... -> End. steps: ('script', label, code) or ('call', label, flow name, in_map, out_map) with
    in_map = {callee input: expression}, out_map = {callee output: 'tw.local.x'}."""
    nodes = []; edges = []; x = 120
    for i, s in enumerate(steps):
        x += 190
        if s[0] == 'script': nodes.append(dict(key=f'n{i}', kind='script', label=s[1], code=s[2], x=x, y=55))
        else:
            target = s[2]; P = app.flow_params[target]
            in_map = [(pn, P[pn], expr) for pn, expr in (s[3] or {}).items()]; out_map = [(pn, P[pn], expr) for pn, expr in (s[4] or {}).items()]
            nodes.append(dict(key=f'n{i}', kind='call', label=s[1], target=target, in_map=in_map, out_map=out_map, x=x, y=55))
    keys = ['start'] + [n['key'] for n in nodes] + ['end']
    for a, b in zip(keys, keys[1:]): edges.append(dict(src=a, dst=b))
    return nodes, edges

def end_state_guid(app, callee_name):
    """Legacy guid of the End exit point of a flow of this app (the end state a link leaving a nested call refers to)."""
    return legacy_guid(app.did('flow', callee_name, 'guid', 'item', 'end'))

def render_flow(app, name, fid, params, variables, nodes, edges, ajax=True, description=''):
    """Complete service flow object (legacy items + BPMN 2 model).
      params    [(name, 'in'|'out', '12.x', is_list, local)]   local = business object of this app
      variables [(name, '12.x', is_list, local)]
      nodes     [dict(key, kind='script', label, code, x, y)]
                [dict(key, kind='call', label, target=<flow name>, in_map=[(param, param id, expression)], out_map=[...], x, y)]
                [dict(key, kind='gateway', label, x, y)]   exclusive gateway: one default edge, the others carry a condition
      edges     [dict(src, dst, condition=None, default=False, ports=('rightCenter', 'leftCenter'))]   src / dst = node keys, 'start', 'end'
    Facts: a link leaving a script has end state Out, one leaving a nested call the guid of the callee's End, the default link of a
    gateway DEFAULT and every other gateway link the guid of its SwitchCondition; the BPMN conditional flow carries the expression and
    the gateway names its default flow; a loop is an edge back to the gateway."""
    did = lambda *p: app.did('flow', name, *p)
    sys_dep = app.dep_sys
    ref = lambda cid, local: ('' if local is True else (local if isinstance(local, str) else sys_dep)) + '/' + cid   # local: True = this app, False = System Data, str = a toolkit dependency id
    P = {n: '2055.' + did('param', n) for n, *_ in params}
    by_key = {n['key']: n for n in nodes}
    for n in nodes:
        if n['kind'] == 'call':
            n['target_id'] = app.flow_id(n['target'])
            tp = app.flow_params[n['target']]
            def typed(entries):
                out = []
                for pn, pid, expr in entries:
                    cid, lst, local = tp['_types'][pn]; out.append((pn, pid, expr, cid, lst, local))
                return out
            n['in_map'] = typed(n['in_map']); n['out_map'] = typed(n['out_map'])
    param_xml = ''.join(f"""        <processParameter name="{attr(n)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processParameterId>{P[n]}</processParameterId>
            <processId>{fid}</processId>
            <parameterType>{1 if d == 'in' else 2}</parameterType>
            <isArrayOf>{'true' if lst else 'false'}</isArrayOf>
            <classId>{ref(cid, local)}</classId>
            <seq>{i + 1}</seq>
            <hasDefault>false</hasDefault>
            <defaultValue isNull="true" />
            <isLocked>false</isLocked>
            <description isNull="true" />
            <guid>{did('guid', 'param', n)}</guid>
            <versionId>{did('version', 'param', n)}</versionId>
        </processParameter>
""" for i, (n, d, cid, lst, local) in enumerate(params))
    var_xml = ''.join(f"""        <processVariable name="{attr(n)}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processVariableId>2056.{did('var', n)}</processVariableId>
            <description isNull="true" />
            <processId>{fid}</processId>
            <namespace>2</namespace>
            <seq>{i + 1}</seq>
            <isArrayOf>{'true' if lst else 'false'}</isArrayOf>
            <isTransient>false</isTransient>
            <classId>{ref(cid, local)}</classId>
            <hasDefault>false</hasDefault>
            <defaultValue isNull="true" />
            <guid>{did('guid', 'var', n)}</guid>
            <versionId>{did('version', 'var', n)}</versionId>
        </processVariable>
""" for i, (n, cid, lst, local) in enumerate(variables))
    data_objects = ''.join(f'<ns17:dataObject itemSubjectRef="itm.{cid}" isCollection="{"true" if lst else "false"}" name="{attr(n)}" id="2056.{did("var", n)}" />\n'
                           for n, cid, lst, local in variables)
    nid = {'start': did('node', 'start'), 'end': did('node', 'end')}
    for n in nodes: nid[n['key']] = did('node', n['key'], n['label'])
    for e in edges:
        e['id'] = ('2027.' + did('flow', 'start')) if e['src'] == 'start' else did('flow', e['src'], e['dst'])
        e['name'] = 'To ' + ('End' if e['dst'] == 'end' else by_key[e['dst']]['label'])
        e['ports'] = e.get('ports') or ('rightCenter', 'leftCenter')
    incoming = {k: [e['id'] for e in edges if e['dst'] == k] for k in nid}
    outgoing = {k: [e['id'] for e in edges if e['src'] == k] for k in nid}
    def end_state(e):
        src = by_key[e['src']]
        if src['kind'] == 'script': return 'Out'
        if src['kind'] == 'call': return end_state_guid(app, src['target'])
        return 'DEFAULT' if e.get('default') else legacy_guid(did('guid', 'condition', e['src'], e['dst']))
    items = []; bpmn_nodes = []
    for n in nodes:
        key = n['key']; label = n['label']; kind = n['kind']; x = n['x']; y = n['y']
        prefix = {'script': '3011', 'call': '3012', 'gateway': '3013'}[kind]
        common = f"""            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processItemId>2025.{nid[key]}</processItemId>
            <processId>{fid}</processId>
            <name>{esc(label)}</name>
            <tWComponentName>{'Script' if kind == 'script' else 'SubProcess' if kind == 'call' else 'Switch'}</tWComponentName>
            <tWComponentId>{prefix}.{did('component', key)}</tWComponentId>
            <isLogEnabled>false</isLogEnabled>
            <isTraceEnabled>false</isTraceEnabled>
            <traceCategory isNull="true" />
            <traceLevel isNull="true" />
            <traceMessage isNull="true" />
            <traceSymbolTable isNull="true" />
            <isExecutionContextTraced>false</isExecutionContextTraced>
            <saveExecutionContext>false</saveExecutionContext>
            <documentation isNull="true" />
            <isErrorHandlerEnabled>false</isErrorHandlerEnabled>
            <errorHandlerItemId isNull="true" />
            <guid>{legacy_guid(did('guid', 'item', key))}</guid>
            <versionId>{did('version', 'item', key)}</versionId>
            <externalServiceRef isNull="true" />
            <externalServiceOp isNull="true" />
            <nodeColor isNull="true" />
            <layoutData x="{x}" y="{y}">
                <errorLink>
                    <controlPoints />
                    <showEndState>false</showEndState>
                    <showName>false</showName>
                </errorLink>
            </layoutData>
"""
        io_lines = ''.join(f'                        <ns17:incoming>{i}</ns17:incoming>\n' for i in incoming[key]) + ''.join(f'                        <ns17:outgoing>{o}</ns17:outgoing>\n' for o in outgoing[key])
        if kind == 'script':
            code = n['code']
            items.append(f"""        <item>
{common}            <TWComponent>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <scriptId>3011.{did('component', key)}</scriptId>
                <scriptTypeId>2</scriptTypeId>
                <isActive>true</isActive>
                <script>{esc(code)}</script>
                <isRule>false</isRule>
                <guid>{did('guid', 'component', key)}</guid>
                <versionId>{did('version', 'component', key)}</versionId>
            </TWComponent>
        </item>
""")
            bpmn_nodes.append(f"""                    <ns17:scriptTask scriptFormat="text/x-javascript" name="{attr(label)}" id="{nid[key]}">
                        <ns17:extensionElements>
                            <ns13:nodeVisualInfo x="{x}" y="{y}" width="95" height="70" />
                        </ns17:extensionElements>
{io_lines}                        <ns17:script>{esc(code)}</ns17:script>
                    </ns17:scriptTask>
""")
        elif kind == 'call':
            sub = '3012.' + did('component', key)
            maps = ''.join(f"""                <parameterMapping name="{attr(pn)}">
                    <lastModified isNull="true" />
                    <lastModifiedBy isNull="true" />
                    <parameterMappingId>2054.{did('mapping', key, pn, isin)}</parameterMappingId>
                    <processParameterId>{pid}</processParameterId>
                    <parameterMappingParentId>{sub}</parameterMappingParentId>
                    <useDefault>false</useDefault>
                    <value>{esc(expr)}</value>
                    <classRef>{ref(cid, local)}</classRef>
                    <isList>{'true' if lst else 'false'}</isList>
                    <isInput>{'true' if isin else 'false'}</isInput>
                    <guid>{did('guid', 'mapping', key, pn, isin)}</guid>
                    <versionId>{did('version', 'mapping', key, pn, isin)}</versionId>
                    <description isNull="true" />
                </parameterMapping>
""" for (isin, group) in ((True, n['in_map']), (False, n['out_map'])) for (pn, pid, expr, cid, lst, local) in group)
            items.append(f"""        <item>
{common}            <TWComponent>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <subProcessId>{sub}</subProcessId>
                <attachedProcessRef>/{n['target_id']}</attachedProcessRef>
                <guid>{did('guid', 'component', key)}</guid>
                <versionId>{did('version', 'component', key)}</versionId>
{maps}            </TWComponent>
        </item>
""")
            assoc = ''.join(f"""                        <ns17:dataInputAssociation>
                            <ns17:targetRef>{pid}</ns17:targetRef>
                            <ns17:assignment>
                                <ns17:from xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns17:tFormalExpression" evaluatesToTypeRef="itm.{cid}">{esc(expr)}</ns17:from>
                            </ns17:assignment>
                        </ns17:dataInputAssociation>
""" for (pn, pid, expr, cid, lst, local) in n['in_map']) + ''.join(f"""                        <ns17:dataOutputAssociation>
                            <ns17:sourceRef>{pid}</ns17:sourceRef>
                            <ns17:assignment>
                                <ns17:to xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns17:tFormalExpression" evaluatesToTypeRef="itm.{cid}">{esc(expr)}</ns17:to>
                            </ns17:assignment>
                        </ns17:dataOutputAssociation>
""" for (pn, pid, expr, cid, lst, local) in n['out_map'])
            bpmn_nodes.append(f"""                    <ns17:callActivity calledElement="{n['target_id']}" name="{attr(label)}" id="{nid[key]}">
                        <ns17:extensionElements>
                            <ns13:nodeVisualInfo x="{x}" y="{y}" width="95" height="70" />
                            <ns4:activityType>CalledProcess</ns4:activityType>
                        </ns17:extensionElements>
{io_lines}{assoc}                    </ns17:callActivity>
""")
        else:
            switch = '3013.' + did('component', key)
            conds = [e for e in edges if e['src'] == key and not e.get('default')]
            default = [e for e in edges if e['src'] == key and e.get('default')][0]
            cond_xml = ''.join(f"""                <SwitchCondition>
                    <lastModified isNull="true" />
                    <lastModifiedBy isNull="true" />
                    <switchConditionId>3014.{did('condition', key, e['dst'])}</switchConditionId>
                    <switchId>{switch}</switchId>
                    <seq>{i + 1}</seq>
                    <endStateId>{legacy_guid(did('guid', 'condition', key, e['dst']))}</endStateId>
                    <condition>{esc(e['condition'])}</condition>
                    <guid>{did('guid', 'switchcondition', key, e['dst'])}</guid>
                    <versionId>{did('version', 'switchcondition', key, e['dst'])}</versionId>
                </SwitchCondition>
""" for i, e in enumerate(conds))
            items.append(f"""        <item>
{common}            <TWComponent>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <switchId>{switch}</switchId>
                <guid>{did('guid', 'component', key)}</guid>
                <versionId>{did('version', 'component', key)}</versionId>
{cond_xml}            </TWComponent>
        </item>
""")
            bpmn_nodes.append(f"""                    <ns17:exclusiveGateway default="{default['id']}" name="{attr(label)}" id="{nid[key]}">
                        <ns17:extensionElements>
                            <ns13:nodeVisualInfo x="{x}" y="{y}" width="32" height="32" />
                        </ns17:extensionElements>
{io_lines}                    </ns17:exclusiveGateway>
""")
    flows = []; links = []
    for e in edges:
        if e['src'] == 'start': continue
        src = by_key[e['src']]; state = end_state(e)
        extra = f'\n                            <ns3:endStateId>{state}</ns3:endStateId>' if src['kind'] == 'call' else ''
        condition = f"""
                        <ns17:conditionExpression xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="ns17:tFormalExpression">{esc(e['condition'])}</ns17:conditionExpression>""" if e.get('condition') else ''
        show_label = 'true' if src['kind'] == 'gateway' else 'false'
        flows.append(f"""                    <ns17:sequenceFlow sourceRef="{nid[e['src']]}" targetRef="{nid[e['dst']]}" name="{attr(e['name'])}" id="{e['id']}">
                        <ns17:extensionElements>
                            <ns3:sequenceFlowImplementation sboSyncEnabled="true" />
                            <ns13:linkVisualInfo>
                                <ns13:sourcePortLocation>{e['ports'][0]}</ns13:sourcePortLocation>
                                <ns13:targetPortLocation>{e['ports'][1]}</ns13:targetPortLocation>
                                <ns13:showLabel>{show_label}</ns13:showLabel>
                                <ns13:showCoachControlLabel>false</ns13:showCoachControlLabel>
                                <ns13:labelPosition>0.0</ns13:labelPosition>
                                <ns13:saveExecutionContext>true</ns13:saveExecutionContext>
                            </ns13:linkVisualInfo>{extra}
                        </ns17:extensionElements>{condition}
                    </ns17:sequenceFlow>
""")
        links.append(f"""        <link name="{attr(e['name'])}">
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processLinkId>2027.{e['id']}</processLinkId>
            <processId>{fid}</processId>
            <description isNull="true" />
            <fromProcessItemId>2025.{nid[e['src']]}</fromProcessItemId>
            <endStateId>{state}</endStateId>
            <toProcessItemId>2025.{nid[e['dst']]}</toProcessItemId>
            <guid>{did('guid', 'link', e['src'], e['dst'])}</guid>
            <versionId>{did('version', 'link', e['src'], e['dst'])}</versionId>
            <layoutData>
                <controlPoints />
                <showEndState>false</showEndState>
                <showName>{show_label}</showName>
            </layoutData>
            <fromItemPort locationId="{e['ports'][0]}" portType="1" />
            <toItemPort locationId="{e['ports'][1]}" portType="2" />
            <fromProcessItemId>2025.{nid[e['src']]}</fromProcessItemId>
            <toProcessItemId>2025.{nid[e['dst']]}</toProcessItemId>
        </link>
""")
    start_edge = [e for e in edges if e['src'] == 'start'][0]; first = nid[start_edge['dst']]
    last = by_key[[e['src'] for e in edges if e['dst'] == 'end'][0]]
    end_x = last['x'] + 230; end_y = last['y'] + 25
    end_item = f"""        <item>
            <lastModified isNull="true" />
            <lastModifiedBy isNull="true" />
            <processItemId>2025.{nid['end']}</processItemId>
            <processId>{fid}</processId>
            <name>End</name>
            <tWComponentName>ExitPoint</tWComponentName>
            <tWComponentId>3008.{did('component', 'end')}</tWComponentId>
            <isLogEnabled>false</isLogEnabled>
            <isTraceEnabled>false</isTraceEnabled>
            <traceCategory isNull="true" />
            <traceLevel isNull="true" />
            <traceMessage isNull="true" />
            <traceSymbolTable isNull="true" />
            <isExecutionContextTraced>false</isExecutionContextTraced>
            <saveExecutionContext>true</saveExecutionContext>
            <documentation isNull="true" />
            <isErrorHandlerEnabled>false</isErrorHandlerEnabled>
            <errorHandlerItemId isNull="true" />
            <guid>{legacy_guid(did('guid', 'item', 'end'))}</guid>
            <versionId>{did('version', 'item', 'end')}</versionId>
            <externalServiceRef isNull="true" />
            <externalServiceOp isNull="true" />
            <nodeColor isNull="true" />
            <layoutData x="{end_x}" y="{end_y}">
                <errorLink>
                    <controlPoints />
                    <showEndState>false</showEndState>
                    <showName>false</showName>
                </errorLink>
            </layoutData>
            <TWComponent>
                <lastModified isNull="true" />
                <lastModifiedBy isNull="true" />
                <exitPointId>3008.{did('component', 'end')}</exitPointId>
                <haltProcess>false</haltProcess>
                <guid>{did('guid', 'component', 'end')}</guid>
                <versionId>{did('version', 'component', 'end')}</versionId>
            </TWComponent>
        </item>
"""
    io = ('<ns17:ioSpecification>' + ''.join(f'<ns17:data{"Input" if d == "in" else "Output"} name="{attr(n)}" itemSubjectRef="itm.{cid}" isCollection="{"true" if lst else "false"}" id="{P[n]}" />' for n, d, cid, lst, local in params)
          + '<ns17:inputSet>' + ''.join(f'<ns17:dataInputRefs>{P[n]}</ns17:dataInputRefs>' for n, d, *_ in params if d == 'in') + '</ns17:inputSet><ns17:outputSet>'
          + ''.join(f'<ns17:dataOutputRefs>{P[n]}</ns17:dataOutputRefs>' for n, d, *_ in params if d == 'out') + '</ns17:outputSet></ns17:ioSpecification>')
    lane_refs = ''.join(f'<ns17:flowNodeRef>{v}</ns17:flowNodeRef>' for v in nid.values())
    end_incoming = ''.join(f'                        <ns17:incoming>{i}</ns17:incoming>\n' for i in incoming['end'])
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<teamworks>
    <process id="{fid}" name="{attr(name)}">
        <lastModified>{NOW}</lastModified>
        <lastModifiedBy>celladmin</lastModifiedBy>
        <processId>{fid}</processId>
        <image isNull="true" />
        <tabGroup isNull="true" />
        <startingProcessItemId>2025.{first}</startingProcessItemId>
        <isRootProcess>false</isRootProcess>
        <processType>12</processType>
        <isErrorHandlerEnabled>false</isErrorHandlerEnabled>
        <errorHandlerItemId isNull="true" />
        <isLoggingVariables>false</isLoggingVariables>
        <isTransactional>false</isTransactional>
        <processTimingLevel isNull="true" />
        <participantRef isNull="true" />
        <exposedType>0</exposedType>
        <isTrackingEnabled>true</isTrackingEnabled>
        <xmlData isNull="true" />
        <cachingType>false</cachingType>
        <itemLabel isNull="true" />
        <cacheLength>0</cacheLength>
        <mobileReady>false</mobileReady>
        <sboSyncEnabled>true</sboSyncEnabled>
        <externalId isNull="true" />
        <isSecured>true</isSecured>
        <isAjaxExposed>{'true' if ajax else 'false'}</isAjaxExposed>
        <description>{esc(description)}</description>
        <guid>{did('guid', 'process')}</guid>
        <versionId>{did('version', 'process')}</versionId>
        <dependencySummary isNull="true" />
        <jsonData isNull="true" />
        <field1 isNull="true" />
        <field2 isNull="true" />
        <field3>0</field3>
        <field4 isNull="true" />
        <field5>false</field5>
        <clobField1 isNull="true" />
        <blobField1 isNull="true" />
{param_xml}{var_xml}{''.join(items)}{end_item}        <startingProcessItemId>2025.{first}</startingProcessItemId>
        <errorHandlerItemId isNull="true" />
        <layoutData noConversion="true">
            <errorLink>
                <controlPoints />
                <showEndState>false</showEndState>
                <showName>false</showName>
            </errorLink>
        </layoutData>
        <startPoint>
            <layoutData x="25" y="80">
                <errorLink>
                    <controlPoints />
                    <showEndState>false</showEndState>
                    <showName>false</showName>
                </errorLink>
            </layoutData>
        </startPoint>
        <startLink>
            <fromPort locationId="rightCenter" portType="1" />
            <toPort locationId="leftCenter" portType="2" />
            <layoutData>
                <controlPoints />
                <showEndState>false</showEndState>
                <showName>false</showName>
            </layoutData>
        </startLink>
        <bpmn2Model>
            <ns17:definitions {BPMN_NS} targetNamespace="" expressionLanguage="http://www.ibm.com/xmlns/prod/bpm/expression-lang/javascript" typeLanguage="http://www.w3.org/2001/XMLSchema">
                <ns17:process name="{attr(name)}" id="{fid}" ns3:executionMode="microflow">
                    <ns17:documentation textFormat="text/plain">{esc(description)}</ns17:documentation>
                    <ns17:extensionElements>
                        <ns3:isSecured>true</ns3:isSecured>
                        <ns3:isAjaxExposed>{'true' if ajax else 'false'}</ns3:isAjaxExposed>
                        <ns3:sboSyncEnabled>true</ns3:sboSyncEnabled>
                    </ns17:extensionElements>
                    {io}
                    <ns17:laneSet id="{did('laneset')}">
                        <ns17:lane name="System" partitionElementRef="{TEAM_SYSTEM}" id="{did('lane')}" ns4:isSystemLane="true">
                            <ns17:extensionElements>
                                <ns13:nodeVisualInfo x="0" y="0" width="3000" height="500" color="#F8F8F8" />
                            </ns17:extensionElements>
                            {lane_refs}
                        </ns17:lane>
                    </ns17:laneSet>
                    {data_objects}
                    <ns17:startEvent isInterrupting="false" parallelMultiple="false" name="Start" id="{nid['start']}">
                        <ns17:extensionElements>
                            <ns13:nodeVisualInfo x="25" y="80" width="24" height="24" color="#F8F8F8" />
                        </ns17:extensionElements>
                        <ns17:outgoing>{start_edge['id']}</ns17:outgoing>
                    </ns17:startEvent>
                    <ns17:endEvent name="End" id="{nid['end']}">
                        <ns17:extensionElements>
                            <ns13:nodeVisualInfo x="{end_x}" y="{end_y}" width="24" height="24" color="#F8F8F8" />
                            <ns4:saveExecutionContext>true</ns4:saveExecutionContext>
                            <ns3:endStateId>{legacy_guid(did('guid', 'item', 'end'))}</ns3:endStateId>
                        </ns17:extensionElements>
{end_incoming}                    </ns17:endEvent>
                    <ns17:sequenceFlow sourceRef="{nid['start']}" targetRef="{first}" name="{attr(start_edge['name'])}" id="{start_edge['id']}">
                        <ns17:extensionElements>
                            <ns13:linkVisualInfo>
                                <ns13:sourcePortLocation>rightCenter</ns13:sourcePortLocation>
                                <ns13:targetPortLocation>leftCenter</ns13:targetPortLocation>
                                <ns13:showLabel>false</ns13:showLabel>
                                <ns13:showCoachControlLabel>false</ns13:showCoachControlLabel>
                                <ns13:labelPosition>0.0</ns13:labelPosition>
                                <ns13:saveExecutionContext>false</ns13:saveExecutionContext>
                            </ns13:linkVisualInfo>
                        </ns17:extensionElements>
                    </ns17:sequenceFlow>
{''.join(bpmn_nodes)}{''.join(flows)}                </ns17:process>
            </ns17:definitions>
        </bpmn2Model>
{''.join(links)}    </process>
</teamworks>
"""
    P['_types'] = {n: (cid, lst, local) for n, d, cid, lst, local in params}
    return xml, P

# ------------------------------------------------------------------------------------------------------ server-side helpers
REST_HELPERS_JS = r'''// kit-rest.js - server file: one HTTP exchange from a server-side script with the JDK client (basic auth of the technical user,
// optional trust-all TLS), used by every service flow that calls a REST API. Environment variables: serverBaseURL, restAuthUser,
// restAuthPassword, restTrustAllCertificates.
function kitEnv(name, fallback) { var v = tw.env[name]; v = (v == null) ? "" : String(v); return (v === "" || v === "undefined" || v === "null") ? fallback : v; }
function kitText(v) { return (v == null) ? "" : String(v); }
// kitHttp(method, url, headers, body) -> { statusCode: number (0 = connection failed), responseBody: text }
// url: absolute, or a path relative to serverBaseURL; headers: plain object; body: text (GET: sent as the query string)
function kitHttp(method, url, headers, body) {
  var out = { statusCode: 0, responseBody: "" };
  method = (kitText(method).toUpperCase() || "GET"); body = kitText(body); url = kitText(url);
  if (url.indexOf("http") !== 0) url = kitEnv("serverBaseURL", "https://localhost:9443").replace(/\/+$/, "") + "/" + url.replace(/^\/+/, "");
  if (method === "GET" && body !== "") { url += (url.indexOf("?") >= 0 ? "&" : "?") + body; body = ""; }
  try {
    var connection = new Packages.java.net.URL(url).openConnection();
    if (kitEnv("restTrustAllCertificates", "false") === "true" && (connection instanceof Packages.javax.net.ssl.HttpsURLConnection)) {
      var trustManager = new Packages.javax.net.ssl.X509TrustManager({ checkClientTrusted: function (c, a) {}, checkServerTrusted: function (c, a) {}, getAcceptedIssuers: function () { return null; } });
      var managers = Packages.java.lang.reflect.Array.newInstance(Packages.javax.net.ssl.TrustManager, 1); managers[0] = trustManager;
      var context = Packages.javax.net.ssl.SSLContext.getInstance("TLS"); context.init(null, managers, new Packages.java.security.SecureRandom());
      connection.setSSLSocketFactory(context.getSocketFactory());
      connection.setHostnameVerifier(new Packages.javax.net.ssl.HostnameVerifier({ verify: function (h, s) { return true; } }));
    }
    connection.setRequestMethod(method); connection.setConnectTimeout(30000); connection.setReadTimeout(180000); connection.setUseCaches(false); connection.setInstanceFollowRedirects(false);
    var user = kitEnv("restAuthUser", "");
    if (user !== "") {
      var credentials = new Packages.java.lang.String(user + ":" + kitEnv("restAuthPassword", "")).getBytes("UTF-8");
      connection.setRequestProperty("Authorization", "Basic " + String(Packages.java.util.Base64.getEncoder().encodeToString(credentials)));
    }
    connection.setRequestProperty("Accept", "application/json");
    if (headers) for (var name in headers) connection.setRequestProperty(kitText(name), kitText(headers[name]));
    if (method === "POST" || method === "PUT" || method === "DELETE") {
      if (body !== "") { connection.setDoOutput(true); var output = connection.getOutputStream(); output.write(new Packages.java.lang.String(body).getBytes("UTF-8")); output.close(); }
      else if (method !== "DELETE") { connection.setDoOutput(true); connection.setRequestProperty("Content-Length", "0"); connection.getOutputStream().close(); }
    }
    var status = connection.getResponseCode();
    var stream = (status >= 400) ? connection.getErrorStream() : connection.getInputStream();
    var text = "";
    if (stream != null) {
      var reader = new Packages.java.io.BufferedReader(new Packages.java.io.InputStreamReader(stream, "UTF-8"));
      var builder = new Packages.java.lang.StringBuilder(); var line;
      while ((line = reader.readLine()) != null) { builder.append(line); builder.append("\n"); }
      reader.close(); text = String(builder.toString());
    }
    connection.disconnect();
    out.statusCode = status; out.responseBody = text;
  } catch (error) { out.statusCode = 0; out.responseBody = "connection failed (" + method + " " + url + "): " + error; }
  return out;
}
// kitJson(text) -> parsed object or null
function kitJson(text) { try { return JSON.parse(text); } catch (e) { return null; } }
'''
STANDARD_ENV = [('serverBaseURL', 'https://localhost:9443', 'Base URL of the server as seen from itself (https://host[:port])'),
                ('restAuthUser', 'celladmin', 'Technical user for server-side REST calls'),
                ('restAuthPassword', 'password', 'Password of the technical user'),
                ('restTrustAllCertificates', 'true', 'true = accept the server certificate (self-signed labs), false = validate it')]
def add_rest_support(app):
    """The four environment variables and the kit-rest.js server file every REST-calling flow needs."""
    for name, default, description in STANDARD_ENV: app.env(name, default, description)
    app.server_file('kit-rest.js', REST_HELPERS_JS, 'kit-rest.js: kitHttp(method, url, headers, body), kitEnv(name, fallback), kitJson(text) for server-side scripts')
