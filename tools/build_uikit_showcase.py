#!/usr/bin/env python3
"""build_uikit_showcase.py - process application "UI Controls Kit" (UICKIT): one dashboard that exercises the UI Toolkit controls the
twxkit helpers did not cover before (inputs, display, structure, navigation / events, SDS charts, service-fed tables and exports),
every tab with a "Read values" button that writes the bound values into the status line so a harness can prove the bindings.

    python3 tools/build_uikit_showcase.py [--snapshot 1.0] [--out UI-Controls-Kit-1.0.twx]

Sample data comes from server-side flows (UK Init at start; UK Chart Data / UK Chart Multi / UK Table Data / UK Lookup Items on demand).
Deep test: tools/pc_uickit_test.py <branch> <cshs> [out.json] [--shots dir]; smoke: tools/dash_test.py <host> <branch> <cshs>.
Design and results: docs/UI-CONTROLS-KIT.md; control facts: baw-knowledge-mcp/knowledge-src/howto/ui-toolkit-controls-catalogue.md.
"""
import argparse, os, sys, struct, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twxkit as k

INIT_JS = r'''// UK Init (server side): header, form defaults, breadcrumb trail, chart series, table rows
function escapeHtml(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
var title = (tw.env.appTitle == null || String(tw.env.appTitle) === "") ? "UI Controls Kit" : String(tw.env.appTitle);
tw.local.headerHtml = '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 4px 12px 4px;border-bottom:1px solid #d9dde3;margin-bottom:10px">'
  + '<div style="font-size:20px;font-weight:600">' + escapeHtml(title) + ' <span style="font-size:13px;font-weight:400;color:#6b7280">UI Toolkit controls proven on the lab</span></div>'
  + '<div style="background:#eef2f7;border-radius:16px;padding:6px 14px;font-size:13px">' + escapeHtml(String(tw.system.user_loginName)) + '</div></div>';

tw.local.form = new tw.object.UKForm();
tw.local.form.amount = 1234.5;
tw.local.form.phone = "";
tw.local.form.choice = "B";
tw.local.form.tags = new tw.object.listOf.String();
tw.local.form.tags.insertIntoList(0, "alpha");
tw.local.form.when = new Date();
tw.local.form.when2 = new Date();
tw.local.form.switchOn = true;
tw.local.form.slider = 40;
tw.local.form.password = "";
tw.local.form.typeAhead = "";
tw.local.form.rich = "<p>Rich <b>text</b> from UK Init</p>";
tw.local.form.lookup = "";
tw.local.form.radioValue = "yes";
tw.local.form.signature = "";
tw.local.form.qr = "https://example.org/uickit";
tw.local.form.longText = "This text is long enough to be cut by the Text Reader control so that a read more link appears; the whole text is still in the bound variable and comes back when the reader is expanded by the user.";
tw.local.form.progress = 30;
tw.local.form.anyValue = "hello";
tw.local.form.dataValue = "initial";
tw.local.form.note = "Notes accept plain text bound to a String variable.";
tw.local.form.searchText = "";
tw.local.eventData = "";

tw.local.trail = new tw.object.listOf.NameValuePair();
var crumbs = [["Home", "home"], ["Requests", "requests"], ["Request 42", "42"]];
for (var c = 0; c < crumbs.length; c++) { var nv = new tw.object.NameValuePair(); nv.name = crumbs[c][0]; nv.value = crumbs[c][1]; tw.local.trail.insertIntoList(tw.local.trail.listLength, nv); }

function series(name, labels, values) {
  var s = new tw.object.DataSeries(); s.seriesName = name; s.dataPoints = new tw.object.listOf.DataPoint();
  for (var i = 0; i < labels.length; i++) { var p = new tw.object.DataPoint(); p.label = labels[i]; p.value = values[i]; s.dataPoints.insertIntoList(s.dataPoints.listLength, p); }
  return s;
}
tw.local.series = series("Tasks per day", ["Mon", "Tue", "Wed", "Thu", "Fri"], [12, 19, 7, 15, 22]);
tw.local.multi = new tw.object.listOf.DataSeries();
tw.local.multi.insertIntoList(0, series("Received", ["Mon", "Tue", "Wed", "Thu", "Fri"], [12, 19, 7, 15, 22]));
tw.local.multi.insertIntoList(1, series("Completed", ["Mon", "Tue", "Wed", "Thu", "Fri"], [8, 14, 9, 11, 20]));

tw.local.rows = new tw.object.listOf.UKRow();
var names = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"];
for (var r = 0; r < names.length; r++) { var row = new tw.object.UKRow(); row.name = names[r]; row.value = "value " + (r + 1); row.amount = (r + 1) * 10.5; tw.local.rows.insertIntoList(tw.local.rows.listLength, row); }
'''

CHART_JS = r'''// UK Chart Data: the single-data-series contract of the SDS charts - inputs `input` (query data) + `drillDownStack`, output `dataSeries`
tw.local.dataSeries = new tw.object.DataSeries();
tw.local.dataSeries.seriesName = "Instances per week" + (tw.local.input != null && String(tw.local.input) !== "" ? " (" + tw.local.input + ")" : "");
tw.local.dataSeries.dataPoints = new tw.object.listOf.DataPoint();
var labels = ["W36", "W37", "W38", "W39", "W40"], values = [31, 45, 28, 52, 39];
for (var i = 0; i < labels.length; i++) { var p = new tw.object.DataPoint(); p.label = labels[i]; p.value = values[i]; tw.local.dataSeries.dataPoints.insertIntoList(tw.local.dataSeries.dataPoints.listLength, p); }
'''

MULTI_JS = r'''// UK Chart Multi: the multi-data-series contract of the Multi Purpose Chart - output `multiDataSeries` (DataSeries[])
function series(name, labels, values) {
  var s = new tw.object.DataSeries(); s.seriesName = name; s.dataPoints = new tw.object.listOf.DataPoint();
  for (var i = 0; i < labels.length; i++) { var p = new tw.object.DataPoint(); p.label = labels[i]; p.value = values[i]; s.dataPoints.insertIntoList(s.dataPoints.listLength, p); }
  return s;
}
tw.local.multiDataSeries = new tw.object.listOf.DataSeries();
tw.local.multiDataSeries.insertIntoList(0, series("Started", ["W36", "W37", "W38", "W39", "W40"], [31, 45, 28, 52, 39]));
tw.local.multiDataSeries.insertIntoList(1, series("Completed", ["W36", "W37", "W38", "W39", "W40"], [25, 40, 30, 44, 41]));
tw.local.multiDataSeries.insertIntoList(2, series("Failed", ["W36", "W37", "W38", "W39", "W40"], [2, 3, 1, 4, 2]));
'''

TABLE_JS = r'''// UK Table Data: the Service Data Table contract - input `data` (UKQuery), output `results` (a list of rows)
tw.local.results = new tw.object.listOf.UKRow();
var filter = (tw.local.data == null || tw.local.data.text == null) ? "" : String(tw.local.data.text).toLowerCase();
var names = ["Server one", "Server two", "Server three", "Client one", "Client two"];
for (var i = 0; i < names.length; i++) {
  if (filter !== "" && names[i].toLowerCase().indexOf(filter) < 0) continue;
  var row = new tw.object.UKRow(); row.name = names[i]; row.value = "service row " + (i + 1); row.amount = (i + 1) * 100;
  tw.local.results.insertIntoList(tw.local.results.listLength, row);
}
'''

LOOKUP_JS = r'''// UK Lookup Items: the item service contract of the select controls - input `data`, output `results` = NameValuePair[] (name = value, value = text)
tw.local.results = new tw.object.listOf.NameValuePair();
var items = [["EMEA", "Europe, Middle East, Africa"], ["AMER", "Americas"], ["APAC", "Asia Pacific"]];
var filter = (tw.local.data == null) ? "" : String(tw.local.data).toLowerCase();
for (var i = 0; i < items.length; i++) {
  if (filter !== "" && items[i][1].toLowerCase().indexOf(filter) < 0) continue;
  var nv = new tw.object.NameValuePair(); nv.name = items[i][0]; nv.value = items[i][1]; tw.local.results.insertIntoList(tw.local.results.listLength, nv);
}
'''

ECHO_JS = r'''// UK Echo Form: the bound values as one line - what the coach controls wrote into tw.local.form
var f = tw.local.data; var parts = [];
function add(name, v) { parts.push(name + "=" + (v == null ? "null" : String(v))); }
if (f == null) { parts.push("form=null"); } else {
  add("amount", f.amount); add("phone", f.phone); add("choice", f.choice);
  var tags = []; for (var i = 0; f.tags != null && i < f.tags.listLength; i++) tags.push(f.tags[i]); add("tags", tags.join("+"));
  add("when", f.when == null ? null : f.when.format("yyyy-MM-dd HH:mm")); add("when2", f.when2 == null ? null : f.when2.format("yyyy-MM-dd"));
  add("switchOn", f.switchOn); add("slider", f.slider); add("passwordLength", f.password == null ? 0 : String(f.password).length); add("typeAhead", f.typeAhead);
  add("lookup", f.lookup); add("radioValue", f.radioValue); add("richText", f.rich == null ? "" : String(f.rich).replace(/<[^>]+>/g, "")); add("signatureLength", f.signature == null ? 0 : String(f.signature).length);
  add("qr", f.qr); add("progress", f.progress); add("anyValue", f.anyValue); add("dataValue", f.dataValue); add("searchText", f.searchText);
}
tw.local.results = new tw.object.UKEcho();
tw.local.results.message = parts.join(" | ");
'''

def make_png(width=96, height=32):
    """A small PNG (blue gradient with a white diagonal) for the Image control - standard library only."""
    def chunk(tag, data): return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    raw = b''
    for y in range(height):
        raw += b'\x00'
        for x in range(width):
            on_line = abs((x * height // width) - y) < 2
            raw += bytes([255, 255, 255]) if on_line else bytes([30 + x * 2 % 120, 90 + y * 3, 200])
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')

def build(snapshot, out):
    app = k.App('UI Controls Kit', 'UICKIT', snapshot, 'UI Controls Kit - every UI Toolkit control family in one dashboard, bound to sample data, with Read values buttons that prove the bindings (twxkit helpers)')
    app.env('appTitle', 'UI Controls Kit', 'Title shown in the dashboard header')
    app.bo('UKForm', [('amount', 'Decimal'), ('phone', 'String'), ('choice', 'String'), ('tags', 'String[]'), ('when', 'Date'), ('when2', 'Date'), ('switchOn', 'Boolean'),
                      ('slider', 'Decimal'), ('password', 'String'), ('typeAhead', 'String'), ('rich', 'String'), ('lookup', 'String'), ('radioValue', 'String'),
                      ('signature', 'String'), ('qr', 'String'), ('longText', 'String'), ('progress', 'Decimal'), ('anyValue', 'String'), ('dataValue', 'String'),
                      ('note', 'String'), ('searchText', 'String')], 'Values bound to the input and display controls')
    app.bo('UKRow', [('name', 'String'), ('value', 'String'), ('amount', 'Decimal')], 'One table row')
    app.bo('UKQuery', [('text', 'String')], 'Query of the service-fed controls')
    app.bo('UKEcho', [('message', 'String')], 'Bound values echoed by UK Echo Form')
    app.web_file('uickit-logo.png', make_png(), 'image/png', 'Sample image of the Image control')
    app.flow('UK Init', outputs=[('headerHtml', 'String'), ('form', 'UKForm'), ('trail', 'NameValuePair[]'), ('series', 'DataSeries'), ('multi', 'DataSeries[]'), ('rows', 'UKRow[]'), ('eventData', 'String')],
             script=INIT_JS, description='Start values of the dashboard (server side)')
    app.flow('UK Chart Data', inputs=[('input', 'String'), ('drillDownStack', 'NameValuePair[]')], outputs=[('dataSeries', 'DataSeries')], script=CHART_JS, description='Single data series for the SDS charts (dataMode From Service)')
    app.flow('UK Chart Multi', inputs=[('input', 'String'), ('drillDownStack', 'NameValuePair[]')], outputs=[('multiDataSeries', 'DataSeries[]')], script=MULTI_JS, description='Several data series for the Multi Purpose Chart')
    app.flow('UK Table Data', inputs=[('data', 'UKQuery')], outputs=[('results', 'UKRow[]')], script=TABLE_JS, description='Rows of the Service Data Table')
    app.flow('UK Echo Form', inputs=[('data', 'UKForm')], outputs=[('results', 'UKEcho')], script=ECHO_JS, description='Echoes the bound form values (proves the bindings: event expressions cannot read tw.local, a Service Call with a bound input can)')
    app.flow('UK Lookup Items', inputs=[('data', 'String')], outputs=[('results', 'NameValuePair[]')], script=LOOKUP_JS, description='Items of the service-fed Single Select')

    def layout(L):
        S = '${StatusLine}.setText'
        ECHO = ' ${SvcEcho}.execute();'   # appends the server-side view of tw.local.form (bound values) to the status line
        # ---- 1. inputs (event expressions cannot read tw.local: control getters here, the bound values through the echo flow)
        read_inputs = (S + '("amount=" + ${Amount}.getValue() + " | phone=" + ${Phone}.getText() + " | choice=" + ${Choice}.getSelectedItem()'
                       ' + " | tags=" + JSON.stringify(${Tags}.getSelectedItems()) + " | when=" + ${When}.getDate() + " | when2=" + ${When2}.getDate()'
                       ' + " | switch=" + ${Sw}.isChecked() + " | slider=" + ${Sl}.getValue() + " | password=" + ${Pwd}.getText().length + " chars"'
                       ' + " | typeAhead=" + ${Ta}.getText() + " | lookup=" + ${Lookup}.getSelectedItem() + " | radioNo=" + ${RbNo}.isSelected()'
                       ' + " | rich=" + ${Rich}.getText().replace(/<[^>]+>/g, "") + " | signatureEmpty=" + ${Sig}.isEmpty());' + ECHO)
        inputs_tab = L.vlayout('InputsTab', [
            L.hlayout('InRow1', [L.decimal('Amount', 'Amount (EUR, 2 places)', 'tw.local.form.amount', places=2, currency='EUR'),
                                 L.masked_text('Phone', 'Phone (mask (###) ###-####)', 'tw.local.form.phone'),
                                 L.password('Pwd', 'Password', 'tw.local.form.password'),
                                 L.type_ahead('Ta', 'Type ahead (alpha, beta, gamma)', 'tw.local.form.typeAhead', items=['alpha', 'beta', 'gamma', 'delta'])]),
            L.hlayout('InRow2', [L.radio_group('Choice', 'Radio group', 'tw.local.form.choice', [('A', 'Option A'), ('B', 'Option B'), ('C', 'Option C')]),
                                 L.multi_select('Tags', 'Multi select', 'tw.local.form.tags[]', [('alpha', 'Alpha'), ('beta', 'Beta'), ('gamma', 'Gamma')]),
                                 L.select_service('Lookup', 'Single select from service', 'tw.local.form.lookup', 'UK Lookup Items', placeHolder='choose a region'),
                                 L.vlayout('RadioPair', [L.radio('RbYes', 'Yes', 'tw.local.form.radioValue', 'yes', 'rb'), L.radio('RbNo', 'No', 'tw.local.form.radioValue', 'no', 'rb')], label='Radio buttons')]),
            L.hlayout('InRow3', [L.date_picker('When2', 'Date picker', 'tw.local.form.when2', enableTodayButton='true'),
                                 L.datetime('When', 'Date time picker', 'tw.local.form.when', time=True),
                                 L.switch('Sw', 'Switch', 'tw.local.form.switchOn', on='Yes', off='No'),
                                 L.slider('Sl', 'Slider (0-100, step 5)', 'tw.local.form.slider', min=0, max=100, step=5)]),
            L.hlayout('InRow4', [L.text_editor('Rich', 'Text editor (rich text)', 'tw.local.form.rich', height='140px')]),
            L.hlayout('InRow5', [L.signature('Sig', 'Signature', 'tw.local.form.signature'), L.qr_code('Qr', 'QR code of form.qr', 'tw.local.form.qr')]),
            L.hlayout('InButtons', [L.button('BtnReadInputs', 'Read values', read_inputs, style='P'),
                                    L.button('BtnClearSig', 'Clear signature', '${Sig}.clear(); ' + S + '("signature cleared, empty=" + ${Sig}.isEmpty());')])], label='Inputs')
        # ---- 2. display
        read_display = (S + '("bar=" + ${Prog}.getProgress() + " | status=" + ${Sbox}.getStatusText()'
                        ' + " | note=" + ${Note1}.getText() + " | badge=" + ${Badge1}.getText() + " | reader=" + ${Reader}.getText().length + " chars, expanded=" + ${Reader}.isExpanded()'
                        ' + " | tooltip=" + ${Tip}.getText() + " | anyValue=" + ${AnyValue}.getText());' + ECHO)
        display_tab = L.vlayout('DisplayTab', [
            L.hlayout('DiRow1', [L.image('Logo', 'uickit-logo.png', width='96px', height='32px'), L.badge('Badge1', 'NEW', style='S'), L.badge('Badge2', 'label', style='I', shape='L'),
                                 L.badge('Badge3', 'tag', style='W', shape='T'), L.icon('Ico', 'bell', style='W', size='28px', on_click=S + '("icon clicked");'),
                                 L.notification('Notif', '3 items need attention', style='W', icon='exclamation-triangle'), L.spacer('Sp1', width='40px', height='10px')]),
            L.line('Line1'),
            L.hlayout('DiRow2', [L.note('Note1', 'Note', 'tw.local.form.note', style='I'),
                                 L.well('Well1', [L.output('WellText', 'Well text', binding=None, show=False, eventON_LOAD='me.setText("Text inside a well with an info icon");')], style='I', icon='info', colorDarkness='D'),
                                 L.tooltip('Tip', 'Type any value; the Variant on the Structure tab shows it', [L.text('AnyValue', 'Any value (tooltip on hover)', 'tw.local.form.anyValue')], style='I')]),
            L.hlayout('DiRow3', [L.progress('Prog', 'Progress', 'tw.local.form.progress', max=100, style='S', striped='true', width=k.responsive('320px')),
                                 L.button('BtnBump', 'Add 10 %', '${Prog}.setProgress(${Prog}.getProgress() + 10); ' + S + '("progress now " + ${Prog}.getProgress());'),
                                 L.status_box('Sbox', 'Status box', style='S', width=k.responsive('320px')),
                                 L.button('BtnStatus', 'Set status', '${Sbox}.setStatusText("saved at " + new Date().toLocaleTimeString()); ${Sbox}.setStatusVisible(false); ${Sbox}.setStatusVisible(true); ' + S + '("status box set");')]),
            L.hlayout('DiRow4', [L.text_reader('Reader', 'Text reader (60 characters)', 'tw.local.form.longText', max_len=60, width=k.responsive('420px')),
                                 L.output('Out1', 'Output text (bound)', 'tw.local.form.longText', show=True, width=k.responsive('420px'))]),
            L.hlayout('DiButtons', [L.button('BtnReadDisplay', 'Read values', read_display, style='P')])], label='Display')
        # ---- 3. structure
        read_structure = (S + '("stack pane=" + ${Stack1}.getCurrentPane() + " | collapsible expanded=" + ${Coll1}.isExpanded() + "/" + ${Coll2}.isExpanded()'
                          ' + " | split panes=" + ${Split}.getPaneCount() + " collapsed0=" + ${Split}.isPaneCollapsed(0) + " | sensor=" + ${Sensor}.getActiveBoxFactor()'
                          ' + " | deferred loaded=" + ${Defer}.isLoaded() + " | variant=" + ${Var1}.getValue() + " | search=" + ${SearchText}.getText());' + ECHO)
        structure_tab = L.vlayout('StructureTab', [
            L.hlayout('StRow1', [L.collapsible('Coll1', 'Collapsible panel 1 (group g)', [L.output('Coll1Text', 't', show=False, eventON_LOAD='me.setText("Body of panel 1");')], group='g', style='P',
                                               on_expand=S + '("panel 1 expanded");', on_collapse=S + '("panel 1 collapsed");', width=k.responsive('45%')),
                                 L.collapsible('Coll2', 'Collapsible panel 2 (group g)', [L.output('Coll2Text', 't', show=False, eventON_LOAD='me.setText("Body of panel 2");')], collapsed=True, group='g', style='I',
                                               on_expand=S + '("panel 2 expanded");', width=k.responsive('45%'))]),
            L.hsplit('Split', [('30%', [L.output('SplitL', 't', show=False, eventON_LOAD='me.setText("Left pane (30 %)");')]), ('70%', [L.output('SplitR', 't', show=False, eventON_LOAD='me.setText("Right pane (70 %) - drag the splitter");')])], height='90px'),
            L.hlayout('StRow2', [L.input_group('Ig', 'Input group (text + search button)', [L.text('SearchText', 'Search', 'tw.local.form.searchText')], button='search',
                                               on_click=S + '("search clicked: " + ${SearchText}.getText());'),
                                 L.caption('Cap', 'Caption box label', L.output('CapText', 't', show=False, eventON_LOAD='me.setText("captioned content");'), placement='L', width='320px'),
                                 L.panel('Pan', 'Panel with header and footer', [L.panel_header('PanH', [L.output('PanHText', 't', show=False, eventON_LOAD='me.setText("Panel header content");')]),
                                                                                 L.output('PanBody', 't', show=False, eventON_LOAD='me.setText("Panel body");'),
                                                                                 L.panel_footer('PanF', [L.output('PanFText', 't', show=False, eventON_LOAD='me.setText("Panel footer content");')])], style='P', width=k.responsive('360px'))]),
            L.hlayout('StRow3', [L.vlayout('StackBox', [L.stack('Stack1', [L.vlayout('StackP0', [L.output('StackT0', 't', show=False, eventON_LOAD='me.setText("Stack pane 0");')]),
                                                                           L.vlayout('StackP1', [L.output('StackT1', 't', show=False, eventON_LOAD='me.setText("Stack pane 1");')])]),
                                                        L.hlayout('StackBtns', [L.button('BtnPane0', 'Pane 0', '${Stack1}.setCurrentPane(0); ' + S + '("stack pane " + ${Stack1}.getCurrentPane());'),
                                                                                L.button('BtnPane1', 'Pane 1', '${Stack1}.setCurrentPane(1); ' + S + '("stack pane " + ${Stack1}.getCurrentPane());')])], label='Stack'),
                                 L.table_layout('Grid', [[[L.output('G00', 't', show=False, eventON_LOAD='me.setText("cell 0,0");')], [L.output('G01', 't', show=False, eventON_LOAD='me.setText("cell 0,1");')]],
                                                         [[L.output('G10', 't', show=False, eventON_LOAD='me.setText("cell 1,0");')], [L.output('G11', 't', show=False, eventON_LOAD='me.setText("cell 1,1");')]]]),
                                 L.variant('Var1', 'Variant (auto select by type)', 'tw.local.form.anyValue', [L.text('VarText', 'String variant'), L.integer('VarInt', 'Integer variant'), L.checkbox('VarBool', 'Boolean variant')])]),
            L.sensor('Sensor', [L.hlayout('SensorRow', [L.output('SensA', 't', show=False, eventON_LOAD='me.setText("responsive child A");'), L.output('SensB', 't', show=False, eventON_LOAD='me.setText("responsive child B (stacked below 600 px)");')],
                                          label='sensor row')], factors=(('narrow', 600), ('wide', 99999)), on_boundary=S + '("responsive boundary: " + JSON.stringify(${Sensor}.getActiveBoxFactor()));'),
            L.hlayout('StRow4', [L.popup_menu('Menu', [L.button('BtnMenu', 'Actions (popup menu)', '${Menu}.setMenuVisible(!${Menu}.isMenuVisible());')], [('open', 'Open', 'folder-open'), ('-',), ('delete', 'Delete', 'trash')], on_item=S + '("menu command: " + command);'),
                                 L.button('BtnDefer', 'Load deferred section', '${Defer}.lazyLoad(0);'),
                                 L.deferred('Defer', [L.output('DeferText', 't', show=False, eventON_LOAD='me.setText("Deferred content is now loaded");')], on_load=S + '("deferred section loaded: " + ${Defer}.isLoaded());')]),
            L.hlayout('StButtons', [L.button('BtnReadStructure', 'Read values', read_structure, style='P')])], label='Structure')
        # ---- 4. events
        read_events = (S + '("config mode=" + ${Config}.getParameter("mode") + " | data=" + ${Data1}.getValue()'
                       ' + " | exit challenged=" + ${Exit1}.isExitChallenged() + " | timer ticks=" + ${Timer1}.getTicks() + " running=" + ${Timer1}.isRunning()'
                       ' + " | crumbs=" + ${Crumbs}.getItemCount() + " | event=" + ${EventSub}.getEventData() + " | device=" + JSON.stringify(${Device}.getDeviceInfo()));' + ECHO)
        events_tab = L.vlayout('EventsTab', [
            L.breadcrumbs('Crumbs', 'Breadcrumbs (bound trail)', 'tw.local.trail[]', on_click=S + '("crumb clicked: " + label + " data=" + (item ? item.data : "")); return false;'),
            L.alerts('AlertArea', style='I', fade=0),
            L.hlayout('EvRow1', [L.button('BtnAlert', 'Append alert', '${AlertArea}.appendAlert("Saved", "The alert area shows this message", "S", 0); ' + S + '("alert appended");'),
                                 L.button('BtnModalAlert', 'Modal alert', '${MAlert}.setText("Hello from the Modal Alert"); ${MAlert}.show();'),
                                 L.button('BtnPublish', 'Publish event', S + '("event published"); bpmext.ui.publishEvent("uickit.ping", JSON.stringify({n: 42, text: "payload"}));'),
                                 L.button('BtnTimer', 'Start timer (1.5 s)', '${Timer1}.start(); ' + S + '("timer started");'),
                                 L.button('BtnExit', 'Toggle exit safeguard', '${Exit1}.setExitChallenged(!${Exit1}.isExitChallenged()); ' + S + '("exit challenged: " + ${Exit1}.isExitChallenged());'),
                                 L.button('BtnData', 'Set data', '${Data1}.setValue("set at " + new Date().toLocaleTimeString()); ' + S + '("data set: " + ${Data1}.getValue());'),
                                 L.button('BtnGeo', 'Request location', '${Geo}.requestUpdate(); ' + S + '("location requested");'),
                                 L.button('BtnCrumb', 'Append crumb', '${Crumbs}.appendItem("Step " + (${Crumbs}.getItemCount() + 1), "x"); ' + S + '("crumbs: " + ${Crumbs}.getItemCount());')]),
            L.modal_alert('MAlert', 'Modal alert title', style='W', button='Got it', on_close=S + '("modal alert closed");'),
            L.event_subscription('EventSub', 'uickit.ping', S + '("event received: " + ${EventSub}.getEventData());', binding='tw.local.eventData'),
            L.timer('Timer1', ms=1500, repeat=False, stopped=True, on_timeout=S + '("timer fired: ticks=" + ${Timer1}.getTicks());'),
            L.exit_safeguard('Exit1', challenge=False, message='Leave the UI Controls Kit?'),
            L.configuration('Config', parameters={'mode': 'demo', 'pageSize': '25'}),
            L.data('Data1', 'tw.local.form.dataValue'),
            L.device_sensor('Device'),
            L.geo_location('Geo', mode='S', on_info=S + '("location: " + JSON.stringify(location));', on_error=S + '("location error: " + (error && error.message ? error.message : JSON.stringify(error)));'),
            L.hlayout('EvButtons', [L.button('BtnReadEvents', 'Read values', read_events, style='P')])], label='Events')
        # ---- 5. charts
        def series_info(cid): return '(function(d){ return d ? (d.name + ":" + (d.items ? d.items.length : 0)) : "none"; })(${' + cid + '}.getDataSeries())'   # getDataSeries() = {name, items[{label, value}]}
        read_charts = S + '("bar=" + ' + series_info('ChartBar') + ' + " | line=" + ' + series_info('ChartLine') + ' + " | pie=" + ' + series_info('ChartPie') + ' + " | donut=" + ' + series_info('ChartDonut') + ' + " | area=" + ' + series_info('ChartArea') + ' + " | step=" + ' + series_info('ChartStep') + ');'
        redraw = '; '.join(f'${{{c}}}.redrawChart()' for c in ['ChartBar', 'ChartLine', 'ChartPie', 'ChartDonut', 'ChartArea', 'ChartStep', 'ChartMulti']) + ';'
        charts_tab = L.vlayout('ChartsTab', [
            L.hlayout('ChRow1', [L.caption('CapBar', 'Bar (series variable)', L.chart('ChartBar', 'bar', series='tw.local.series', height=220, style='P'), placement='T', width='32%'),
                                 L.caption('CapLine', 'Line (service)', L.chart('ChartLine', 'line', flow='UK Chart Data', height=220, style='I', spline='true'), placement='T', width='32%'),
                                 L.caption('CapPie', 'Pie (series variable)', L.chart('ChartPie', 'pie', series='tw.local.series', height=220), placement='T', width='32%')]),
            L.hlayout('ChRow2', [L.caption('CapDonut', 'Donut (service)', L.chart('ChartDonut', 'donut', flow='UK Chart Data', height=220), placement='T', width='32%'),
                                 L.caption('CapArea', 'Area (series variable)', L.chart('ChartArea', 'area', series='tw.local.series', height=220, style='S'), placement='T', width='32%'),
                                 L.caption('CapStep', 'Step (service)', L.chart('ChartStep', 'step', flow='UK Chart Data', height=220, style='W', showArea='true'), placement='T', width='32%')]),
            L.caption('CapMulti', 'Multi purpose chart (three series from a service, bar)', L.chart('ChartMulti', 'multi', flow='UK Chart Multi', height=260, chart_type='B'), placement='T', width='100%'),
            L.hlayout('ChButtons', [L.button('BtnReadCharts', 'Read values', read_charts, style='P'), L.button('BtnRedraw', 'Redraw charts', redraw + ' ' + S + '("charts redrawn");'),
                                    L.button('BtnRefresh', 'Refresh service charts', '${ChartLine}.refresh(); ${ChartDonut}.refresh(); ${ChartStep}.refresh(); ${ChartMulti}.refresh(); ' + S + '("service charts refreshed");')])], label='Charts')
        # ---- 6. data
        read_data = S + '("rows=" + ${Rows}.getRecordCount() + " selected=" + JSON.stringify(${Rows}.getSelectedRecord()) + " | service rows=" + ${SvcRows}.getRecordCount() + " | query=" + ${Query}.getText());'
        data_tab = L.vlayout('DataTab', [
            L.table('Rows', 'Table bound to tw.local.rows', 'tw.local.rows', [('name', 'Name'), ('value', 'Value'), ('amount', 'Amount')], page=10),
            L.hlayout('DaRow1', [L.data_export('ExportCsv', 'Export bound rows (CSV)', binding='tw.local.rows[]', file_type='csv', file_name='uickit-rows', headers=['Name', 'Value', 'Amount'], style='P'),
                                 L.data_export('ExportXlsx', 'Export bound rows (XLSX)', binding='tw.local.rows[]', file_type='xlsx', file_name='uickit-rows')]),
            L.data_export('ExportTable', 'Export the table above (CSV, tableName)', table='Rows', file_type='csv', file_name='uickit-table'),
            L.hlayout('DaRow2', [L.text('Query', 'Filter (service data table)', 'tw.local.query.text'),
                                 L.button('BtnSvcRows', 'Refresh service table', '${SvcRows}.refresh(true); ' + S + '("service table refreshed");')]),
            L.service_table('SvcRows', 'Service Data Table (UK Table Data)', 'UK Table Data', 'tw.local.svcRows', [('name', 'Name'), ('value', 'Value'), ('amount', 'Amount')], input_binding='tw.local.query', page=10),
            L.hlayout('DaButtons', [L.button('BtnReadData', 'Read values', read_data, style='P')])], label='Data')
        return [L.output('Header', 'Header', 'tw.local.headerHtml', html=True), L.status_line(),
                L.service('SvcEcho', 'UK Echo Form', 'tw.local.form', 'tw.local.echo', on_result='${StatusLine}.setText(${StatusLine}.getText() + " || bound: " + (result ? result.message : ""));'),
                L.tabs('MainTabs', 'UI Controls Kit', [inputs_tab, display_tab, structure_tab, events_tab, charts_tab, data_tab], eventON_TABCHANGE='if (tabIndex == 4) { ' + redraw + ' }')]
    app.cshs('UI Controls Kit Dashboard', layout,
             variables=[('headerHtml', 'String'), ('form', 'UKForm', 'new'), ('trail', 'NameValuePair[]'), ('series', 'DataSeries'), ('multi', 'DataSeries[]'), ('rows', 'UKRow[]'),
                        ('query', 'UKQuery', 'new'), ('eventData', 'String'), ('svcRows', 'UKRow[]'), ('echo', 'UKEcho')],
             init='UK Init', exposed='Dashboard', team='All Users', description='UI Controls Kit dashboard: Inputs, Display, Structure, Events, Charts, Data')
    ids = app.write(out)
    print('\n'.join(app.log)); print(f'-> {out}\n   dashboard playback: {list(ids["playback"].values())[0]}')
    return ids

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--snapshot', default='1.0'); p.add_argument('--out')
    a = p.parse_args(); build(a.snapshot, a.out or f'UI-Controls-Kit-{a.snapshot}.twx')
