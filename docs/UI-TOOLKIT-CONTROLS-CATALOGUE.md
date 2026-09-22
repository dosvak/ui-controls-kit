# UI Toolkit controls catalogue (BPM UI, toolkit SYSBPMUI, BPM 8.6 onwards)

What every control of the standard UI Toolkit expects (binding type), what its important configuration options are (with the enum
values that work), which events it fires and how to use them in coach event expressions, how it sizes itself, the pitfalls met, and
the `twxkit.py` layout helper that renders it. Everything marked *verified* was played back in the process app **UI Controls Kit**
(UICKIT, package `UI-Controls-Kit-1.2.twx`, generator `build_uikit_showcase.py`, deep test `pc_uickit_test.py`, 67 checks) on 8.6.2 and
on 26; the option catalogue itself (names, types, enum values, content boxes) comes from the toolkit's own view definitions of 8.6.0.0
and is the same list `twxkit.VIEW_OPTIONS` guards at build time.

## Choosing a control

| Need | Controls | Notes |
|---|---|---|
| **Text and numbers in** | Text, Text Area, Password, Masked Text, Type Ahead Text, Text Editor (rich), Integer, Decimal, Slider | String / Integer / Decimal bindings; Decimal and Integer format (currency, separators), Masked Text keeps the mask literals in the value |
| **Choices in** | Checkbox, Switch (Boolean); Single Select, Radio Button Group, Radio Button (one value); Multi Select, Checkbox Group (list); Variant (type-driven) | selects take a static list, a config-option list or an Ajax service; the bound value is the item `name`, the shown text the item `value` |
| **Dates in** | Date Time Picker (date + optional time), Date Picker (date only, older) | both bind a Date; the Date Time Picker is the one to use |
| **Signatures, codes** | Signature (PNG data URL in a String), QR Code (shows a String) | |
| **Show values** | Output Text (HTML allowed), Text Reader (long text with read more), Note, Badge, Notification, Icon, Image, Progress Bar, Status Box, Line, Spacer | Badge / Notification / Tooltip texts are set with `setText()` (On load) or the formula option, they have no binding |
| **Group and arrange** | Vertical / Horizontal Layout, Panel (+ Panel Header / Footer), Well, Caption Box, Collapsible Panel, Tab Section, Stack, Horizontal Split, Table Layout (Row / Cell), Input Group, Tooltip, Responsive Sensor, Deferred Section, Modal Section, Popup Menu | every one has ContentBox1; Caption Box and Tooltip and Input Group wrap exactly one control |
| **Lists of records** | Table (bound list, child controls = columns), Service Data Table (rows from an Ajax flow into a bound list), Data Export (csv / xlsx of a list or a table) | |
| **Charts** | Bar / Line / Area / Step / Pie / Donut Chart SDS (one data series), Multi Purpose Chart (several series, switchable type) | data = UI Toolkit DataSeries {seriesName, dataPoints[{label, value}]} from a variable or from an Ajax flow |
| **Actions and navigation** | Button, Link, Breadcrumbs, Popup Menu, Navigation Event (fires a coach boundary event) | |
| **Invisible helpers** | Service Call, Data, Event Subscription, Timer, Configuration, Exit Safeguard, Alerts (area), Modal Alert, Device Sensor, Geo Location, Geo Coder, Places, OpenLayers API, Map, Style, Video | Alerts / Modal Alert render on demand; Geo / Map / Places need the browser's permission or a map provider |
| **Inside a task only** | Default Inline User Task Template | the layout of an inline user task; not for dashboards |

## Common pitfalls across controls (all verified)

* **Event expressions cannot see `tw.local`.** `ReferenceError: tw is not defined` in an On click / On change expression. Read values with
  the control API (`${Amount}.getValue()`, `${Tags}.getSelectedItems()`), and when the *bound* value is needed in an expression, send it
  through a Service Call whose `inputData` is the variable (`L.service('SvcEcho', 'UK Echo Form', 'tw.local.form', ...)`, then
  `${SvcEcho}.execute()` and read `result` in its On result expression) - the framework resolves the bound option, the expression does not.
* **Undeclared config option = HTTP 500 at playback** (`generatecoachng`). Only the option names of the view's definition may appear in the
  layout; `twxkit.Layout.ref()` refuses others at build time. The list per view is `twxkit.VIEW_OPTIONS`.
* **Option value formats.** Enum options take the bare letter (`colorStyle` `P`); adaptive options (width, height, sizeStyle, labelPlacement,
  most Boolean display switches) accept the designer's responsive JSON `{"isResponsiveData":true,"values":[{"deviceConfigID":"LargeID","value":...}]}`
  (`twxkit.responsive(v)`) and also a plain value at runtime; list options are JSON arrays of records (`staticList`, `columnSpecs`,
  `paneSpecs`, `menuItems`, `boxFactors`, `parameters`, `colHeaders`, `itemList`); a bound option is `<valueType>dynamic</valueType>` with the
  variable path (`('dynamic', 'tw.local.series')` in twxkit); a SERVICE option (`attachedService`, `sdsDataService`, `mdsDataService`,
  `dataService`, `itemService`) holds the `1.` id of an Ajax service flow of the same app.
* **Service contracts are positional by parameter name**: Service Call = `data` in / `results` out; select item services = `data` in /
  `results` NameValuePair[] out; Service Data Table = `data` in / `results` list out; SDS chart = `input` (String) + `drillDownStack`
  (NameValuePair[]) in / `dataSeries` (DataSeries) out; Multi Purpose Chart in multi mode = `multiDataSeries` (DataSeries[]) out. The
  controls call `POST /rest/bpm/wle/v1/service/<flow id>` themselves (the Service Call control uses `/coachflow/service/`).
* **No backslashes in event expressions** (the coach XML escaping breaks them); regular expressions like `/<[^>]+>/g` are fine.
* **Lists in a client-side human service are initialised by a server-side flow**, not by variable defaults: bind Multi Select / Table /
  Breadcrumbs / charts to lists an init flow fills.
* **Handlers run synchronously**: `bpmext.ui.publishEvent(...)` runs the subscriber's On published event before the next statement of the
  publishing expression; an On result of a Service Call runs later (asynchronous). Write the status line in the right order.
* **Hidden tabs and sizes**: charts and split panes drawn inside a hidden tab pane are sized to the page width; call `redrawChart()` /
  `refresh()` from the Tab Section's On tab changed (`tabIndex` is the new pane) or from a button.
* **Getters answer the control's own model, not the variable**: `getDataSeries()` returns `{name, items[{label, value}]}` (not the DataSeries
  field names); Stack `getCurrentPane()` is `null` until `setCurrentPane()` ran once on an unbound stack; Signature `isEmpty()` is false until
  `clear()` ran once; Status Box `getStatusText()` is the help-text metadata.
* **Playwright / automation facts**: a Decimal input ignores `locator.fill()` (type on the keyboard and press Tab); a Slider has no input
  element (`page.ui.get('Sl').setValue(65)`); `page.ui.get('<viewid>')` in the coach frame returns any control by its layout id; a Popup
  Menu renders its `ul.dropdown-menu.open` outside the control's element; hidden tab panes keep their DOM (`.tab-hidden`).
* **Keep option labels short** in custom views and give every environment variable a non-empty default (import failures otherwise).

## Inputs

## Text
Purpose: one-line text input. Binding: String. Options: `width`, `placeHolder`, `regExp` (validation), `selectAll`, `sizeStyle` D/L/S,
`labelPlacement` T/L, `labelWidth`, `tabIndex`. Events: `eventON_CHANGE` (bound data changed), `eventON_INPUT` (each keystroke), `eventON_FOCUS`,
`eventON_BLUR`, `eventON_LOAD`. API: `getText()` / `setText()` (setText updates the binding), `focus()`. Verified (kit helper `L.text(id, label, binding, width)`).

## Text Area
Purpose: multi-line text. Binding: String. Options: `width`, `height` (the only size option, no rows), `placeHolder`, `regExp`, `printOverflow`.
Events as Text. Verified. Helper `L.text_area(id, label, binding, height)`.

## Password
Purpose: masked one-line input. Binding: String. Options and events as Text (`width`, `placeHolder`, `sizeStyle`, `eventON_INPUT`). Verified
(typed value reaches the binding, length read back). Helper `L.password(id, label, binding, width)`.

## Masked Text
Purpose: fixed-format input. Binding: String - the bound value **keeps the literal characters of the mask** (typing 5551234567 with mask
`(###) ###-####` binds `(555) 123-4567`). Options: `mask` (`#` digit, `a` letter, `*` either, everything else literal), `autoclear` (clear an
incomplete value), `monospace`, `placeHolder`, `width`. Events: `eventON_CHANGE`, `eventON_INPUT`, focus / blur. API: `getText()` / `setText()`,
`setMask()`. Verified. Helper `L.masked_text(id, label, binding, mask, width)`.

## Type Ahead Text
Purpose: text with suggestions. Binding: String (the typed text, not an item). Options: `itemLookupMode` E start empty / S items from
service / L items from list, `itemList` = JSON list of strings for mode L, `itemService` (mode S), `dropdownItems` (max shown), `placeHolder`,
`width`. Events: `eventON_CHANGE` with `newText`, `oldText`. API: `getText()` / `setText()`, `isListItem(text)`. Verified with a static list.
Helper `L.type_ahead(id, label, binding, items=[...])`.

## Text Editor
Purpose: rich text (HTML) editor. Binding: String = the HTML. Options: `width`, `height`, `showStatus` (status bar with the current element),
`colorMap` / `colorCols` / `colorRows` (palette). Events: change / focus / blur. API: `getText()` (HTML) / `setText()`. Verified (the init
HTML round-trips to the binding). Helper `L.text_editor(id, label, binding, height)`.

## Integer
Purpose: whole number. Binding: Integer. Options: `placeHolder`, `prefix` / `postfix`, `numericFormatting` auto (user locale) / custom with
`thousandsSep`, `hideThousandsSeparator`, `width`. Events: `eventON_CHANGE` with `newValue`, `oldValue`; `eventON_FORMAT` (`value`,
`formattedValue`, `format` - return a string to override). API: `getValue()` / `setValue()`. Verified (kit helper `L.integer`).

## Decimal
Purpose: decimal number, optionally a currency. Binding: Decimal. Options: `decimalPlaces`, `currency` = ISO code (`EUR`, `USD`, ... `NONE`) -
formats with the currency symbol (`€99.75` shown, `99.75` bound), `currencySymbol` overrides the symbol, `decimalSep` / `thousandsSep` /
`numericFormatting` custom|auto, `prefix` / `postfix`, `placeHolder`, `width`. Events as Integer. API: `getValue()` / `setValue()`.
Pitfall: the control re-formats on blur; automation must type (keyboard) and Tab, `fill()` is ignored. Verified. Helper
`L.decimal(id, label, binding, places=2, currency='EUR')`.

## Slider
Purpose: numeric input by dragging. Binding: Decimal. Options: `min`, `max`, `step`, `vertical`, `colorStyle` D/P/I/S/W/E, `width` /
`height`, `handleWidth`, `radius`. Event: `eventON_CHANGE`. API: `getValue()` / `setValue(v)` (writes the binding). No text input inside
(noUiSlider). Verified. Helper `L.slider(id, label, binding, min, max, step)`.

## Checkbox
Purpose: one Boolean. Binding: Boolean. Events: change / focus / blur. API `isChecked()` / `setChecked()`. Verified (kit helper `L.checkbox`).

## Switch
Purpose: on / off toggle with labels. Binding: Boolean. Options: `onLabel` / `offLabel` (text, or icon names when `labelType` I),
`colorStyle` D/P/I/S/W/G, `shapeStyle` D default / S square / M modern, `sizeStyle`. Event `eventON_CHANGE`. API `isChecked()` / `setChecked()` /
`click()`. Verified (click toggles the binding). Helper `L.switch(id, label, binding, on='Yes', off='No')`.

## Single Select
Purpose: drop-down, one value. Binding: ANY (a String variable in practice; a business object with `businessDataMapping`). Options:
`itemLookupMode` E/S/L/B, `staticList` = JSON `[{"name": bound value, "value": shown text}]` (mode L), `itemService` + `inputData` (mode S:
an Ajax flow with input `data` and output `results` NameValuePair[]), `itemList` (mode B: a bound list of business objects) with `dataMapping`
{optionValueProperty, optionDisplayProperty}, `placeHolder`, `width`, `sizeStyle`. Events: `eventON_CHANGE`, `eventON_SVCITEMS`,
`eventON_SVCERROR`. API: `getSelectedItem()`, `setSelectedItem(value)`, `clearItems()`, `setItem(idx, value, text)`, `appendItem()`,
`reloadServiceItems(input)`. Verified: static list (kit) and the service mode (the flow is called at load, the placeholder is the first option,
the selection writes the `name`). Helpers `L.select(id, label, binding, items)` and `L.select_service(id, label, binding, flow)`.

## Radio Button Group
Purpose: one value as radio buttons. Binding: ANY (String). Options like Single Select (`staticList` etc.), `labelPlacement`. Event
`eventON_CHANGE`. API `getSelectedItem()` / `setSelectedItem()`. Verified (the DOM inputs carry the `name` as `value`). Helper
`L.radio_group(id, label, binding, items)`.

## Radio Button
Purpose: one radio button of a group across the coach. Binding: ANY shared by the buttons of a `groupName`; selecting it writes
`valueWhenSelected`. Event `eventON_SELECTED`. API `isSelected()` / `setSelected()`. Verified. Helper `L.radio(id, label, binding, value, group)`.

## Multi Select
Purpose: list box with several selections. Binding: a **list** variable (`tw.local.form.tags[]`), receives the `name` values. Options as
Single Select (`staticList`, service mode, `dataMapping`, `businessDataMapping`), `width`, `sizeStyle`. Events: change, service items /
error, focus / blur. API: `getSelectedItems()` (plain array), `setSelectedItems()`, `getSelectedIndices()`, `appendItem()`, `clearItems()`.
Verified: selecting two options gave the bound list `alpha+beta` (server side `listLength` 2). Helper `L.multi_select(id, label, binding, items)`.

## Checkbox Group
Purpose: several checkboxes, several values. Binding: list (ANY[]). `staticList` with name == value is the convention used by the kit.
API `getSelectedItems()`, `addSelectedItem()`, `removeSelectedItem()`, `setOptionDisabled()`. Verified (kit helper `L.checkbox_group`).

## Date Time Picker
Purpose: date with optional time. Binding: Date. Options: `includeTimePicker` true/false, `format` (Java SimpleDateFormat, e.g.
`yyyy-MM-dd HH:mm`), `type` TI text input / I inline calendar, `enableTodayButton` / `enableClearButton`, `startDate` / `endDate` (Date),
`blackoutDates` (Date list) / `blackoutDateStart` / `blackoutDateEnd`, `disabledWeekDays` {Sunday..Saturday Booleans}, `weekStart` 0-6,
`startView` 0 month / 1 year / 2 decade, `minViewMode`, `orientation` A/TA/BA/AL/TL/BL/AR/TR/BR, `colorStyle` D/I/S/W/E, `calendarType`
gregorian / hebrew / islamic, `enableCalendarIcon`, `yearSelectorStyle` Default / Modern, `hideHeader`. Events: `eventON_CHANGE`,
`eventON_BEFORE_SHOW_DAY` (`date`, return a class / tooltip for the day cell). API: `getDate()` / `setDate()`, `setStart()` / `setEnd()`,
`setBlackoutDates([...])`, `open()` / `close()`, `clear()`. Verified (a Date set by the init flow shows and echoes back as `2026-09-22 12:56`).
Helper `L.datetime(id, label, binding, time=True, fmt=None)`; `L.date()` is the same control without the time part.

## Date Picker
Purpose: the older date-only picker. Binding: Date. Options like the Date Time Picker but `format` uses lower-case tokens (`mm/dd/yyyy`)
and `startDate` / `endDate` are Strings in that format; no time, no blackout list. API `getDate()` / `setDate()`, `setStart("06/01/2015")`.
Verified. Helper `L.date_picker(id, label, binding, fmt=None)`. Prefer the Date Time Picker for new work.

## Signature
Purpose: draw a signature. Binding: String = PNG data URL after drawing. Options: `width` / `height` (px), `inkColor`, `colorStyle`,
`borderWidth`, `radius`, `shadow`. Event `eventON_CHANGED`. API `clear()`, `isEmpty()` (false until `clear()` ran once), `obfuscate()`.
Verified (clear + isEmpty). Helper `L.signature(id, label, binding, width, height)`.

## QR Code
Purpose: render a QR code of a String. Binding: String. Options: `width` / `height`, `errorCorrectionLevel` L/M/Q/H, `backgroundImageURL`,
`labelPlacement`. Event `eventON_CHANGE`. API `getQRCode()` / `setQRCode()`. Verified (renders the bound URL). Helper `L.qr_code(id, label, binding, size)`.

## Display

## Output Text
Purpose: read-only text or HTML. Binding: String. Options: `allowHTML` (render the value as HTML - the kit's header and message pattern),
`width`, `textAlignment` D/L/C/R, `colorStyle` H/D/M/L/P/I/S/W/G, `sizeStyle` D/R/X/G/L/S/M, `weightStyle` D/S/N/M/B, `labelPlacement`,
`labelWeightNormal`. API `getText()` / `setText()`. Verified (kit helpers `L.output`, `L.status_line`, `L.hidden`).

## Text Reader
Purpose: long read-only text with a "Show more" / "Show less" link. Binding: String. Options: `maxTextLen` (default 128), `readMoreHint` /
`readLessHint`, `initiallyExpanded`, `width` / `height`. Events: `eventON_EXPAND`, `eventON_COLLAPSE`, `eventON_CLICK`. API `getText()`
(the whole text), `isExpanded()`, `setExpanded()`, `toggleExpanded()`. Verified. Helper `L.text_reader(id, label, binding, max_len)`.

## Note
Purpose: a coloured note box with a heading. Binding: String = the note text (or `setText()` on load). Options: `colorStyle` D/P/S/I/W/G,
`labelStyle` H4 default / H1 / H2 / H3, `width`. Event `eventON_CLICK`. Verified (bound). Helper `L.note(id, title, binding=None, text=None, style, heading)`.

## Badge
Purpose: small coloured badge / label / tag. No binding: the text comes from the formula option or `setText()` in `eventON_LOAD`
(`me.setText("NEW")` - `me` is the control inside its own handlers). Options: `colorStyle` D/P/I/S/W/E, `shapeStyle` B badge / L label / T tag.
Event `eventON_CLICK`. Verified (three shapes). Helper `L.badge(id, text, style, shape)`.

## Notification
Purpose: an inline notification with an icon. No binding (`setText()` on load). Options: `colorStyle` D/P/I/S/W/E, `icon` (Font Awesome
name, `fa-` optional). Event `eventON_CLICK`. Verified. Helper `L.notification(id, text, style, icon)`.

## Icon
Purpose: a clickable Font Awesome icon. Binding: Boolean `isClicked` (optional). Options: `icon`, `colorStyle` D/P/I/S/W/G/T, `iconSize`
(font size), `size` (width), `outline`, `radius`, `showAsIcon` (static), `preventMultipleClicks`. Events: `eventON_CLICK` (return false to
stop the boundary event), `eventON_BOUNDARYEVT`. API `setIcon()`, `click()`. Verified. Helper `L.icon(id, icon, style, size, on_click)`.

## Image
Purpose: show an image. Binding: URL (optional). Unbound: `defaultURL` + `defaultURLType` Web (a managed web file, resolved through
`getManagedAssetUrl` of the app named in `defaultAppAcronym`, default the toolkit) or External (absolute URL); bound: `urlType` +
`appAcronym`. Options: `width` / `height`, `radius`. Events `eventON_CLICK`. API `setImage(name, type)`. Verified with a web file of the
same app (`/teamworks/webasset/<snapshot>/W/uickit-logo.png`, natural size read back). Helper `L.image(id, url, app=None, external=False, width, height)`.

## Progress Bar
Purpose: a bar for a value between 0 and `maxValue`. Binding: Decimal. Options: `maxValue` (100 %), `colorStyle` D/P/I/S/W/G, `striped`,
`active` (moving stripes), `width` / `height`, `radius`. Event `eventON_CLICK`. API `getProgress()` / `setProgress()` (writes the binding),
`setMaximum()`. Verified (bound 30, +10 through the API echoed as 40). Helper `L.progress(id, label, binding, max, style)`.

## Status Box
Purpose: a status strip next to a form. No binding; ContentBox1 optional. Options: `colorStyle` D/P/S/I/W/E, `statusStyle` N plain
paragraph (default) / D strip / K dark / S simple, `showStatus`, `floatStatus`, `showValidationErrors`, `htmlStatus`. Event `eventON_SCLICK`.
API `setStatusText(text)` (stores the help-text metadata) and `setStatusVisible(bool)`. Pitfall (verified): the strip element is created only
when the status becomes visible while a text is set - `setStatusText(t); setStatusVisible(false); setStatusVisible(true);` shows it,
`setStatusText` alone shows nothing. Helper `L.status_box(id, label, style, status_style='D')`.

## Line
Purpose: horizontal rule. No binding, no options. Verified. Helper `L.line(id)`.

## Spacer
Purpose: empty box. Options `width`, `height`, `animateSizeChgs`. Verified. Helper `L.spacer(id, width, height)`.

## Structure

## Vertical Layout / Horizontal Layout
Purpose: the containers (ContentBox1). Binding: a list (optional - a bound layout repeats its content per item, `startEmpty`, `deferLoad`,
`loadBatchSize`). Options: `layoutFlow` V / Y vertical tight / P horizontal / H inline scroll / I horizontal tight / W auto-wrap,
`hAlignment` J/L/C/R, `vAlignment` T/M/B, `width` / `height`, `sensor` + `behaviors` (responsive). Events `eventON_LOAD`, `eventON_RESUPD`.
Verified (kit helpers `L.vlayout`, `L.hlayout(wrap=True)`).

## Panel
Purpose: titled box. ContentBox1. Options: `colorStyle` D/P/S/I/W/G/T, `lightColor`, `colorfulBody`, `icon`, `footerText`, `width` /
`height`. Event `eventON_ICONCLICK`. API `setTitle()`, `setFooter(text, html)`. Verified (kit helper `L.panel`).

## Panel Header / Panel Footer
Purpose: header / footer strips inside a Panel (first / last child of its ContentBox1); each has ContentBox1. Verified together with a Panel.
Helpers `L.panel_header(id, children)`, `L.panel_footer(id, children)`.

## Well
Purpose: shaded box with an optional icon. ContentBox1. Options: `colorStyle` D/P/I/S/W/G, `colorDarkness` N/D/R, `icon` + `iconSize` +
`iconPosition` TR/TL/BR/BL, `vAlignment`, `padding`, `radius`, `width` / `height`. Event `eventON_CLICK` (anywhere inside). Verified.
Helper `L.well(id, children, style, icon)`.

## Caption Box
Purpose: a label placed T/L/B/R of **exactly one** child (ContentBox1 takes one control). Options: `labelPlacement`, `labelWidth`,
`labelHorizAlign` L/C/R, `labelVertAlign` T/M/B, `labelColorStyle`, `labelSizeStyle`, `labelWeightStyle`, `shrinkToContent`, `width`.
Verified (used as the titled frame around each chart). Helper `L.caption(id, label, child, placement, width)`.

## Collapsible Panel
Purpose: a panel that folds. ContentBox1. Options: `initiallyCollapsed`, `panelGroup` (one open panel per group - opening one closes the
others), `colorStyle` D/P/S/I/W/G, `width` / `height`. Events: `eventON_EXPAND`, `eventON_COLLAPSE`. API `expand()` / `collapse()` /
`isExpanded()`. DOM: the header is `div.accordion-toggle[role=button]`. Verified (group behaviour and both events). Helper
`L.collapsible(id, title, children, collapsed, group, style, on_expand, on_collapse)`.

## Tab Section
Purpose: tabs; every child of ContentBox1 is a pane, its `@label` the tab title. Binding: Integer pane index (optional). Options:
`defaultPaneIdx`, `colorStyle` D/P/S/I/W/G, `tabsStyle` D/S, `sizeStyle`. Event `eventON_TABCHANGE` with `oldTabIndex`, `tabIndex`
(used to redraw charts of the shown pane). API `setCurrentPane(i)`, `getCurrentPane()`, `getTabCount()`, `setTabText()`. DOM: tab links
`a[id^="tabs-<id>-tab-text"]`, hidden panes carry `tab-hidden`. Verified (kit helper `L.tabs`).

## Stack
Purpose: several panes, one visible. ContentBox1 (one pane per child). Binding: Integer pane index (optional). Option `defaultPaneIdx`
(-1 = none). API `setCurrentPane(i)`, `getCurrentPane()` (null until a pane was set on an unbound stack), `getPaneCount()`. Verified.
Helper `L.stack(id, panes, default=0)`.

## Horizontal Split
Purpose: side-by-side panes with a draggable splitter. ContentBox1, one pane per child. Options: `height` (the control needs an explicit
height, default 100 % of a container that must have one), `paneSpecs` = JSON `[{"size": "30%", "collapsedSize": "", "splitterThickness": "",
"handleLocation": "M"}, ...]` (handle N none / M middle / S top / E bottom). Events: `eventON_COLLAPSE`, `eventON_EXPAND` with `panelIndex`.
API `collapsePane(i)`, `expandPane(i)`, `togglePane(i)`, `isPaneCollapsed(i)`, `getPaneCount()`. Verified (2 panes, 30 / 70 %).
Helper `L.hsplit(id, [('30%', [...]), ('70%', [...])], height)`.

## Table Layout / Table Layout Row / Table Layout Cell
Purpose: an HTML table grid: Table Layout > Row > Cell (each ContentBox1). Options on the layout: `borderSpacing`, `borderCollapse` S/C.
Verified (2 x 2). Helper `L.table_layout(id, rows=[[cell children, ...], ...])`.

## Input Group
Purpose: one input control (ContentBox1) with an attached button. Options: `buttonKind` I icon / T text / M menu, `buttonInfo` = icon name
or text, `buttonLocation` L/R, `buttonColorStyle` D/P/I/S/W/G, `labelPlacement`, `labelWidth`, `width`. Event `eventON_CLICK` (the button).
DOM: `span.input-group-addon[role=button]`. Verified. Helper `L.input_group(id, label, [L.text(...)], button='search', on_click=...)`.

## Tooltip
Purpose: hover text around one control (ContentBox1). Text: formula option or `setText()` on load. Options: `showOnHover`, `showTooltip`
(visible at load), `horizontalPos` L/C/R, `verticalPos` T/B, `colorStyle`, `sizeStyle` D/L/X, `htmlText`, `showLabel`, `width`.
API `getText()` / `setText()`, `setTooltipVisible()`. Verified. Helper `L.tooltip(id, text, [child], style)`.

## Responsive Sensor
Purpose: box factors for responsive layouts. ContentBox1. Option `boxFactors` = JSON `[{"name": "narrow", "widthUpTo": 600}, ...]`; the
layouts inside declare `behaviors` per factor (`[{"boxFactorName": "narrow", "childLayout": "V", "childAlign": ..., "visibility": V/N/H, ...}]`).
Event `eventON_BOUNDARY` (fires at load with the initial factor, then on every crossing). API `getActiveBoxFactor()` (the factor name),
`pause()` / `resume()` / `refreshLayout()`. Verified. Helper `L.sensor(id, children, factors, on_boundary)`.

## Variant
Purpose: show one of several candidate controls (ContentBox1) depending on the bound value's type or an index. Binding: ANY. Options:
`autoSelectControl`, `initialControlIndex` (expression, 0-based). Event `eventON_CHANGE`. API `showControl(i)`, `getValue()` /
`setValue()`, `getCurrentChildView()`. Verified (a String binding shows the Text child). Helper `L.variant(id, label, binding, children)`.

## Deferred Section
Purpose: render ContentBox1 later. Options: `autoLoad` + `autoLoadDelay` ms, or `lazyLoad(delayMs)` from an event. Event
`eventON_SECLOAD` (after loading). API `isLoaded()`, `getDeferredView(i)`. Verified. Helper `L.deferred(id, children, auto, delay, on_load)`.

## Modal Section
Purpose: a modal dialog with primary / secondary buttons. ContentBox1. Options: `@visibility` HIDDEN until `show()`, `modalWellWidth`,
`showModalButtonGroup`, `primaryBtnText` / `secondaryBtnText`, `colorStyle` D/P/I/S/W/G/B, `closeOnClick`. Events: `eventPRIMARY_ON_CLICK`,
`eventSECONDARY_ON_CLICK`, `eventON_SHOW`, `eventON_CLOSE`. API `show()`, `setVisible()`, `setPrimaryButtonEnabled()`. Verified (kit helper `L.modal`).

## Popup Menu
Purpose: a drop-down menu around the control in ContentBox1. Nothing opens it by itself: the inner control's click calls
`${Menu}.setMenuVisible(!${Menu}.isMenuVisible())`. Option `menuItems` = JSON `[{"command": "open", "itemType": "L", "itemText": "Open",
"icon": "folder-open", "badgeText": "", "badgeShape": "N|S|R", "badgeColor": "D|P|I|S|W|G"}, {"itemType": "S"}]` (L label / S separator / H section
header), `horizAlign` L/R/A, `vertAlign` B/T/A, `castShadow`, `menuSticky`, `width`. Events: `eventON_ICLICK` with `command`, `eventON_SHOW`,
`eventON_CLOSE`. API `setMenuVisible()`, `isMenuVisible()`, `addMenuItem()`, `setMenuItemBadgeText()`. DOM: the open menu is
`ul.dropdown-menu.open` rendered outside the control's element. Verified. Helper `L.popup_menu(id, [button], items, on_item)`.

## Navigation, events and data helpers

## Button
Purpose: click. Binding: Boolean `isClicked` (optional). Options: `colorStyle` D/P/I/S/W/G/B, `shapeStyle` D/R/F, `sizeStyle` D/L/S/X,
`outline`, `ghostMode`, `icon` + `iconLocation` L/R, `width`, `preventMultipleClicks`. Events: `eventON_CLICK` (return false to stop the
boundary event), `eventON_BOUNDARYEVT`. A button without On click fires the coach boundary event (task coach exits). Verified (kit helper `L.button`).

## Link
Purpose: hyperlink or boundary event. Binding: Boolean. Options: `linkType` U url / B boundary event, `linkURL` (dynamic expression in the kit),
`sameWindow`, `linkText`, text styles. Verified (kit helper `L.link`).

## Breadcrumbs
Purpose: a trail. Binding: NameValuePair[] (`name` = text, `value` = data). Event `eventON_ITEM_CLICK` with `label` and `item`
= {label, level, data}; the trail is trimmed to the clicked item unless the expression returns false. API `appendItem(text, data)`,
`setItemAt()`, `getItemAt()`, `getItemCount()`, `trim(i)`, `removeLastItem()`. Verified. Helper `L.breadcrumbs(id, label, 'tw.local.trail[]', on_click)`.

## Alerts
Purpose: an area where alerts appear. No binding. Options: `alertColorStyle` P/I/S/W/G default, `autoFadeDelay` ms (0 = stay), `animate`,
`dense`, `darkStyle`, `alertTopics` (JSON list of strings; `*` = unspecified topics), `showIcon` (Carbon theme). API
`appendAlert(title, text, style, timeoutMs[, id, data])` (returns the id), `getAlert(id)`, `clear()`; alerts can also be published as events
on topic `ALERT*GENERAL` / `ALERT*<topic>`. Events: `eventON_ALERTCLICK`, `eventON_ALERTCLOSE`, `eventON_ALERTEXPIRED` with `item`.
Verified. Helper `L.alerts(id, style, fade)`.

## Modal Alert
Purpose: a one-button message dialog. Label = title. Options: `colorStyle` P/I/S/W/G, `buttonLabel`. API `setText()`, `setTitle()`,
`show()`, `setVisible()`. Events `eventON_SHOW`, `eventON_CLOSE`. Verified. Helper `L.modal_alert(id, title, style, button, on_close)`.

## Event Subscription
Purpose: react to `bpmext.ui.publishEvent(name, data)` from anywhere in the page (other controls, other coaches on the page). Binding:
the payload (use a String variable and publish strings / JSON text - an object payload comes back wrapped as a coach object). Options:
`eventName`. Event `eventON_EVENT` (runs synchronously inside `publishEvent`). API `getEventData()`, `setEventName()`. Verified.
Helper `L.event_subscription(id, event_name, on_event, binding)`.

## Timer
Purpose: timed events. Options: `timeout` ms, `repeat`, `stopped` (start later with `start()`). Events `eventON_TIMEOUT`,
`eventON_BOUNDARYEVT`. API `start()`, `stop()`, `toggle()`, `isRunning()`, `getTicks()`, `resetTicks()`, `setTimeout()`. Verified.
Helper `L.timer(id, ms, repeat, stopped, on_timeout)`.

## Exit Safeguard
Purpose: the browser's leave-page challenge. Options `challengeByDefault`, `message`. API `setExitChallenged(bool)`, `isExitChallenged()`,
`setChallengeMessage()`. Verified (API; the browser dialog itself is outside the coach). Helper `L.exit_safeguard(id, challenge, message)`.

## Configuration
Purpose: page-level settings and named parameters. Options: `parameters` = JSON `[{"name": "mode", "value": "demo"}]`, `debugging`,
`showLog`, `lastFirst`, `globalTextDir` D/L/R, `locale`, `i18nService`. API `getParameter(name)`, `setDebugging()`, `setGlobalTextDirection()`.
Verified. Helper `L.configuration('Config', parameters={...})`.

## Data
Purpose: an invisible value holder bound to a variable. Binding: ANY. Events `eventON_CHANGE`. API `getValue()` / `setValue()` (writes the
binding - verified through the echo flow). Helper `L.data(id, binding)`.

## Service Call
Purpose: run an Ajax service flow (input `data`, output `results`) from an expression. Binding: the result. Options: `attachedService`
(flow id), `inputData` (bound variable), `autoRun` (also on input change), `busyIndicator` X/S/R/C. Events: `eventON_SVCINVOKE`,
`eventON_SVCBEFORERESULT`, `eventON_SVCRESULT` (`result`), `eventON_SVCERROR` (`error.errorText`). API `execute([input])`, `getResult()`,
`getLastError()`. Verified (kit helper `L.service`; the bound-value echo pattern of the kit relies on it).

## Device Sensor
Purpose: browser / device facts. Binding: DeviceInfo (optional). API `getDeviceInfo()` = {os, browserName, browserMajorVersion,
screenWidth, clientWidth, language, isIPad, isIPhone, isAndroid, isIEMobile}, `refresh()`. Verified. Helper `L.device_sensor('Device')`.

## Geo Location
Purpose: the browser's geolocation. Binding: GeoLocation {latitude, longitude, accuracy, altitude, heading, speed, time, timestamp,
errorCode, errorMessage} (optional). Options: `monitoringMode` L once on load / C continuous / S stopped, `highAccuracy`, `geoTimeout`,
`maxAge`. Events: `eventON_LOCINFOREQ`, `eventON_LOCINFO` (`location`), `eventON_LOCINFOERR` (`error`). API `requestUpdate()`,
`calculateDistance(lat1, lon1, lat2, lon2)`. Verified up to the permission prompt (a headless browser answers "User denied request for
Geolocation" through the error event). Helper `L.geo_location(id, mode='S', on_info, on_error)`.

## Geo Coder, Places, OpenLayers API, Map
Not exercised: Geo Coder (binding StreetAddress, `location` LatLong option, address events) and Places (`requestNearbySearch`) need the
provider behind the OpenLayers API control (`APIKey`, `eventON_APILOADED`), and Map (`mapSource` osm / bing, `mapType` 0/1/2, `centerLat` /
`centerLong`, `zoom` 0-19, `marker`, `eventON_MARKERCLICK`, API `setCenter()` / `addMarker({lat, lng})`) draws tiles from the map provider on
the internet. They work only with network access to that provider (and a key for Bing / Google-backed services), which the lab does not
have - no twxkit helper; use `L.ref(id, 'Map', L.std(...), options={...})` with the option names above when a provider is available.

## Navigation Event
Purpose: fire a coach boundary event from an expression (`fire()`, `confirmAndFire(message)`) with `eventData`. Not exercised in the
dashboard: a boundary event leaves the coach, which ends a dashboard human service; use it in task coaches whose flow continues after the coach.

## Style
Purpose: load extra CSS files / switch the theme (`styleSpecs` = [{cssFile, cssType Web/External, appAcronym, themeName}], API
`setTheme(name)`). Not exercised (needs a CSS web file); the kit sets coach CSS through `App.cshs(css=...)` instead.

## Video
Purpose: HTML5 video (`sourceType` video/mp4 / webm / flv / application/x-mpegURL, `posterURL`, `autoPreload`, `autoPlay`, `tracks`
WebVTT web files; binding String = source URL). Not exercised (needs a media file); a managed web file URL from
`tw.system.model.findManagedFileByPath` is the documented source.

## Default Inline User Task Template
The layout template of an inline user task (input / output messages, twelve content boxes). Only meaningful inside a task; skipped.

## Data: lists, tables and exports

## Table
Purpose: rows of a bound list. Binding: the list (`tw.local.rows[]`); columns = child controls in ContentBox1 bound to
`tw.local.rows.currentItem.<field>` (their `@label` is the header), `columnSpecs` in the same order (`renderAs` V coach view / S seamless /
H simple HTML / C custom, `visibility` V/R/N, `sortable`, `width`, `label`). Options: `selectionMode` N/S/M, `showAddButton` /
`showDeleteButton`, `showFooter`, `showPager`, `showPageSizer`, `pageSize`, `showTableStats`, `tableStyle` D/E/B/S/H/C, `colorStyle`,
`highlightSel`, `height` (sticky header), `allowWrap`, `showPopups`, `headerFooterStyle` Default / Modern, `deferLoad`. Events:
`eventON_ROWSEL` (`row`), `eventON_ALLROWS` (`all`), `eventON_ADDREC`, `eventON_DELREC`, `eventON_SORTING` (`col`, `order`),
`eventON_NEWCELL`, `eventON_PAGESIZERCHANGE`. API `getRecords()`, `getSelectedRecord(s)()`, `getRecordCount()`, `appendElement()`,
`setAllRecordsSelected()`, `search()`, `sort()`. Verified (kit helper `L.table`; the harness selects a row with a real mouse click on the first cell).

## Service Data Table
Purpose: a table whose rows come from an Ajax flow. Binding: a list variable that receives the rows (`tw.local.svcRows[]`); columns =
child controls bound to `currentItem.<field>` **exactly like the Table** - the control counts its columns from the children of
ContentBox1 (a Service Data Table with `columnSpecs` only shows the selection column). Options: `dataService` (flow id; input `data`, output
`results`), `queryData` (bound input), `startEmpty`, `columnSpecs` (renderAs H simple HTML / C custom), the Table's paging / style options,
`height`. Events: `eventON_DATALOADED`, `eventON_DATAERROR`, plus the Table events. API `refresh(true)` (re-runs the flow with the current
query data), `setQueryData()`, `getRecordCount()`, `clear()`. Verified: 5 rows at load, filtered to 2 after `refresh(true)` with a changed
bound query. Helper `L.service_table(id, title, flow, 'tw.local.svcRows', cols, input_binding='tw.local.query')`.

## Data Export
Purpose: a button that downloads a list as csv or xlsx. Binding: a list (`tw.local.rows[]`, every field a column, `colOrder` picks fields)
or `tableName` = the layout id of a Table found from the export's parent view (`view.ui.getParent().ui.get(tableName)` - a sibling in the
same layout, not a cousin). Options: `fileType` csv / xlsx, `defName` (file name), `colNames` (headers), `colHeaders` (JSON list of
strings), `colSpecs` ([{columnFormatString}]), `inclInvis`, button styles. Events: `eventON_CLICK`, `eventON_CELLEXPT` (per cell: return a
replacement value / null / {format}). API `exportFile()`, `setTargetControl()`, `setFileType()`, `setFileName()`, `setColumnHeaders()`.
Verified: csv (129 bytes, UTF-8 BOM, `Name,Value,Amount`) and xlsx (15 kB) of the bound list, csv of a Table by name. Helper
`L.data_export(id, label, binding='tw.local.rows[]' | table='Rows', file_type, file_name, headers)`.

## Charts

## Bar / Line / Area / Step / Pie / Donut Chart SDS
Purpose: one data series. No binding. Data: `dataMode` B = from the config option `singleDataSeries` (bind it dynamically to a
DataSeries variable filled by a server-side flow: `tw.object.DataSeries` with `seriesName` and `dataPoints` = `tw.object.listOf.DataPoint`
{label, value}), or `dataMode` S = from `sdsDataService` (an Ajax flow with inputs `input` String and `drillDownStack` NameValuePair[] and
output `dataSeries` DataSeries; optional outputs `availableForDrillDown`, `drillDownStack` for drill-down menus). Options: `height` (px,
adaptive), `showTooltip`, `showValueLabels`, `dataSeriesColorStyle` P/I/S/W/G/L (bar / line / area / step) or L/P/I/S/W/G (pie / donut),
`dataSeriesCustomColorStyle` (NameValuePair colours), `backgroundColorStyle` T/P/I/S/W/G, `xyAxisColorStyle` N/K/C/L/D, `horizontalGridlineStyle`
N/L/D, `maxYAxisTicks`, `yAxisTickPrecision`, `minYAxisValue` / `maxYAxisValue`, `xAxisCulling`, `maxXTickCount`, `xLabelRotation`,
`xAxisHeight`, `pointSize` (line / area), `spline` (line) / `splineArea` (area) / `showArea` (step), `legendPlacement` N/B/M (pie / donut),
`radius`, `padding`, `enableMenu` + `showBreadCrumbs` (drill-down). Events: `eventON_REFRESH` (data arrived, before drawing),
`eventON_CLICK` (return false to suppress the menu), `eventON_MENUCMD` (`action`). API: `refresh()` (re-run the flow), `redrawChart()`
(re-size, e.g. after a tab switch), `getDataSeries()` = `{name, items[{label, value}]}`, `setQueryData()` (the `input` of the flow),
`getSelectedDataPoint()`, `addHorizontalLine(value, label)`, `transform(type, seriesNames)`, `drillUp()`. Sizing: the chart fills its
container's width at draw time - draw or redraw it when the container is visible. Verified: all six kinds, three fed from a variable and
three from the flow, with the same series read back through `getDataSeries()` and the flows called at load and on `refresh()`. Helper
`L.chart(id, kind, series='tw.local.series' | flow='UK Chart Data', height, style)`; the toolkit types are declared in `twxkit.UITK_TYPES`
(`DataSeries`, `DataPoint`) so flows and variables can use them.

## Multi Purpose Chart
Purpose: several series and a switchable chart type. `mds` true + `multiDataSeries` (bound DataSeries[] variable) or `mdsDataService`
(flow output `multiDataSeries` DataSeries[]); `mds` false makes it a single-series chart like the ones above. Options: `defaultChartType`
B bar / L line / A area / S spline / R area spline / T step / E area step / P pie / D donut, `tooltipStyle` N/G/U, `legendPlacement`, the axis
options above. API as the SDS charts plus `transform("bar", [...])`, `groupSeries()`, `showSeries()` / `hideSeries()`. Verified with three
series from a flow drawn as grouped bars. Helper `L.chart(id, 'multi', flow=..., chart_type='B')`.

## Tooling summary

* `twxkit.Layout` helpers: decimal, radio_group, radio, multi_select, select_service, date_picker, datetime, masked_text, password,
  type_ahead, text_editor, text_reader, switch, slider, signature, qr_code, badge, icon, image, line, note, notification, well, tooltip,
  progress, spacer, status_box, collapsible, hsplit, input_group, caption, stack, table_layout, sensor, variant, popup_menu, deferred,
  panel_header, panel_footer, breadcrumbs, alerts, modal_alert, exit_safeguard, event_subscription, timer, configuration, data,
  device_sensor, geo_location, data_export, chart, service_table - next to the earlier output, text, text_area, integer, checkbox, select,
  checkbox_group, date, button, link, hlayout, vlayout, panel, tabs, table, service, modal, hidden, custom, status_line, message_modal.
* `twxkit.UITK_TYPES`: DataSeries, DataPoint, DeviceInfo, GeoLocation, StreetAddress, LatLong (referenced through the UI Toolkit dependency).
* Proof: `build_uikit_showcase.py` (the app), `pc_uickit_test.py` (67 checks: inputs typed and echoed, every event, charts, exports),
  `dash_test.py` (every tab, no JavaScript errors); design and results in the workspace document UI-CONTROLS-KIT.
