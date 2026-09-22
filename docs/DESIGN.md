# UI Controls Kit (UICKIT) - the UI Toolkit controls proven on the lab

One process application, one dashboard, every UI Toolkit (SYSBPMUI) control family the twxkit helpers did not cover before, each bound
to sample data and each tab with a **Read values** button that writes the values into the status line so that a harness can prove the
bindings. Built by `tools/build_uikit_showcase.py` on `tools/twxkit.py` (standard library only, no base export); the facts learned are
written up for the BAW Knowledge MCP in `baw-knowledge-mcp/knowledge-src/howto/ui-toolkit-controls-catalogue.md`.

| Item | Value |
|---|---|
| Package | `UI-Controls-Kit-1.2.twx` (workspace root and `baw-knowledge-mcp/packages/`), ids `tools/uickit_ids.json` |
| App / branch / dashboard (deterministic) | project `2066.9fa9e1cf-4a46-5571-b380-aeaa18a13b5e`, branch `2063.e27a498c-1f63-59d1-a2ec-8f6515db88ce`, CSHS `1.1b71ba20-c515-505f-82bd-54623bf32496` |
| 8.6.2 snapshots | 1.0 `2064.73cb4267-8588-50b8-9a33-f469ce0178f3` (Read values failed: `tw` undefined), 1.1 `2064.061fbbea-acad-5d36-ae81-82d0aa757e7b` (61/67), 1.2 `2064.5df4b9b9-1d9e-5268-b682-f9f1b2fdd4ab` (67/67) |
| Playback | `<process-center-host>/teamworks/executecf?modelID=1.1b71ba20-c515-505f-82bd-54623bf32496&branchID=2063.e27a498c-1f63-59d1-a2ec-8f6515db88ce` |
| Env var | `appTitle` (header title, read by UK Init) |

## What the dashboard shows

Header (Output Text with HTML from the init flow), one page-level status line, a Service Call `SvcEcho` bound to `tw.local.form`
(the echo of the bound values), then the Tab Section `MainTabs`:

| Tab | Controls | Sample data |
|---|---|---|
| Inputs | Decimal (EUR), Masked Text, Password, Type Ahead Text, Radio Button Group, Multi Select, Single Select fed by a service, two Radio Buttons, Date Picker, Date Time Picker, Switch, Slider, Text Editor, Signature, QR Code | `tw.local.form` (UKForm) from UK Init; items from UK Lookup Items |
| Display | Image (web file of the app), three Badges, Icon, Notification, Line, Note (bound), Well with icon, Tooltip around a Text, Progress Bar, Status Box, Text Reader, Output Text, Spacer | form fields |
| Structure | two Collapsible Panels in a group, Horizontal Split, Input Group, Caption Box, Panel with Panel Header / Footer, Stack with buttons, Table Layout 2 x 2, Variant, Responsive Sensor, Popup Menu around a Button, Deferred Section | static texts set On load |
| Events | Breadcrumbs (bound trail), Alerts, Modal Alert, Event Subscription, Timer, Exit Safeguard, Configuration, Data, Device Sensor, Geo Location + one button per control | `tw.local.trail`, `tw.local.eventData` |
| Charts | Bar / Pie / Area from the variable `tw.local.series`, Line / Donut / Step from the flow UK Chart Data, Multi Purpose Chart (three series from UK Chart Multi) | DataSeries of the UI Toolkit |
| Data | Table (6 rows), Data Export csv / xlsx of the bound list and csv of the Table by name, Service Data Table fed by UK Table Data with a bound query | `tw.local.rows`, `tw.local.svcRows`, `tw.local.query` |

Flows (all Ajax, script only): UK Init (start values), UK Echo Form (`data` UKForm -> `results.message`), UK Chart Data (`input`,
`drillDownStack` -> `dataSeries`), UK Chart Multi (-> `multiDataSeries`), UK Table Data (`data` UKQuery -> `results` UKRow[]),
UK Lookup Items (`data` String -> `results` NameValuePair[]).

## Build, import, test

```
python3 tools/build_uikit_showcase.py --snapshot 1.2 --out UI-Controls-Kit-1.2.twx      # + UI-Controls-Kit-1.2.ids.json
python3 tools/pc_import.py UI-Controls-Kit-1.2.twx                                       # 8.6.2 console wizard, ~7 min
python3 tools/pc_uickit_test.py 2063.e27a498c-1f63-59d1-a2ec-8f6515db88ce 1.1b71ba20-c515-505f-82bd-54623bf32496 out.json --shots shots/
python3 tools/dash_test.py <process-center-host> 2063.e27a498c-1f63-59d1-a2ec-8f6515db88ce 1.1b71ba20-c515-505f-82bd-54623bf32496
BAW_HOST=<workflow-center-26-host> python3 tools/pc_import.py UI-Controls-Kit-1.2.twx        # BAW 26 lab (Workflow Center)
BAW_HOST=<workflow-center-26-host> python3 tools/pc_uickit_test.py <branch> <cshs> out26.json --shots shots26/
```

A changed build needs a new snapshot name (the server caches per snapshot; twxkit derives versionIds from the content).
`tools/twxkit_sample.py` must still build after every edit of `twxkit.py`.

## Results

| Run | Result |
|---|---|
| 8.6.2, snapshot 1.0 | dashboard renders, dash_test 0 JS errors; the Read values buttons failed: `ReferenceError: tw is not defined` in every event expression that read `tw.local` |
| 8.6.2, snapshot 1.1 | 61/67 deep checks, 0 JS errors; open: Decimal typing / Slider automation, Status Box strip, Popup Menu item lookup, Stack / Signature start states |
| 8.6.2, snapshot 1.2 | **67/67**, 0 JS errors, 0 failed calls; dash_test 6 tabs, 0 errors, 17 REST calls |
| BAW 26 (the BAW 26 lab), snapshot 1.2 | imported through the Workflow Center console with the same ids (`2064.5df4b9b9-...`); **67/67** deep checks, 0 JS errors, 0 failed calls; dash_test 6 tabs, 0 errors, 19 REST calls (`BAW_HOST=<workflow-center-26-host>`, screenshots in the `--shots` folder of that run) |

Screenshots per tab (start / after interaction): `01-inputs-start` ... `11-data-after` in the harness `--shots` folder.

### What failed on the way and how it was fixed

| Finding | Fix |
|---|---|
| Coach event expressions have no `tw` object (`ReferenceError: tw is not defined`) | values are read with control getters; the bound values are proven through a Service Call whose `inputData` is `tw.local.form` (flow UK Echo Form echoes them) |
| Service Data Table showed 5 empty rows: it counts its columns from the children of its content box | bound to `tw.local.svcRows[]` with Output Text children on `currentItem.<field>`, like the Table (`L.service_table` renders them) |
| Status Box `setStatusText()` showed nothing | the strip element is created when the status becomes visible while a text is set: `setStatusText(t); setStatusVisible(false); setStatusVisible(true);`; `statusStyle` default N is a plain paragraph, the helper defaults to D |
| Popup Menu never opened on the button click | nothing opens it by itself: the inner button's On click calls `${Menu}.setMenuVisible(!${Menu}.isMenuVisible())`; the open `ul.dropdown-menu` renders outside the control's element |
| Event Subscription seemed silent | its handler runs synchronously inside `bpmext.ui.publishEvent`, the publishing expression overwrote the status afterwards; publish strings (an object payload comes back as a coach object) |
| `getDataSeries()` gave `undefined` for `seriesName` | it answers `{name, items[{label, value}]}` |
| Stack `getCurrentPane()` null at start, Signature `isEmpty()` false at start | facts, not defects: null until `setCurrentPane()` ran (unbound), false until `clear()` ran |
| Harness: Decimal ignored `fill()`, Slider has no input, Collapsible header is `div.accordion-toggle`, Input Group button is `span.input-group-addon` | keyboard typing + Tab, `page.ui.get('Sl').setValue(65)` (the coach frame exposes `page.ui.get(id)`), selectors adjusted |
| BAW 26 sign-on form differs (`#username`, `#log_in`, hidden `j_username`) | `bawenv.login` detects it; `dash_test.py` uses `bawenv.login` |

### Controls not in the app and why

Map, Geo Coder, Places, OpenLayers API (a map provider on the internet and a key), Video (a media file), Style (a CSS web file / theme),
Navigation Event (a boundary event ends a dashboard service), Default Inline User Task Template (inline task only). Geo Location is in the
app but a headless browser denies the permission (the error event proves the wiring).
