# UI Controls Kit (UICKIT)

One dashboard that exercises the **IBM BAW UI Toolkit controls** beyond the basic form fields - decimal, masked text, password,
type-ahead, text editor, radio groups, multi select, service-fed select, date and date-time pickers, switch, slider, signature, QR
code, output / reader / note / badge / notification / icon / image / progress / status box, collapsible panel, split, input group,
caption box, panel header and footer, stack, table layout, responsive sensor, variant, deferred section, popup menu, well, tooltip,
breadcrumbs, alerts, modal alert, event subscription, timer, exit safeguard, configuration, data, device sensor, geo location, the
SDS charts (bar, line, pie, donut, area, step, multi purpose) from a bound series and from a service, table, service data table and
data export (CSV / XLSX). Every tab has a **Read values** button that proves the bindings, and the package was played back with a
67-check deep test on IBM BPM 8.6.2 / BAW 20 and on BAW 26.

**Target:** IBM BPM 8.6.2, IBM BAW 20-26 (traditional) and CP4BA (Workflow Authoring / Studio import). Out-of-the-box building
blocks only (System Data, UI Toolkit, one client-side human service, six small service flows) - no third-party toolkit.

## Install

1. Import `packages/UI-Controls-Kit-1.2.twx` (Process Center / Workflow Center console: *Import Process App*; CP4BA: Business Automation Studio > *Import*).
2. Open the dashboard *UI Controls Kit* from Process Portal (exposed to All Users) or through the playback URL of the human service.

## Documents

* [docs/UI-TOOLKIT-CONTROLS-CATALOGUE.md](docs/UI-TOOLKIT-CONTROLS-CATALOGUE.md) - one section per control: binding type, the
  options and enum values that work, events, sizing, pitfalls met, and the generator helper that renders it.
* [docs/DESIGN.md](docs/DESIGN.md) - what the app shows tab by tab, how to rebuild and test it, the failures met and how they were fixed.

## Rebuilding and testing

`tools/build_uikit_showcase.py [--snapshot 1.2]` renders the package with `tools/twxkit.py` (standard library only, no base export);
`tools/pc_uickit_test.py <branch> <cshs> out.json` runs the 67 checks with Playwright. The generator, the kit and the catalogue are
also served to AI agents by the **BAW Knowledge MCP server** (`https://bawmcp.dosvak.com/mcp`, see
[dosvak/baw-mcp](https://github.com/dosvak/baw-mcp)): `get_package('ui controls kit')`, `get_tool('build_uikit_showcase.py')`,
`get_topic('howto-ui-toolkit-controls-catalogue')`.
