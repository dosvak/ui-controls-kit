#!/usr/bin/env python3
"""Deep test of the UI Controls Kit dashboard (UICKIT) in playback: every tab, inputs typed / picked, the Read values button of each tab,
the event controls (alert, modal alert, published event, timer, deferred section, popup menu, breadcrumbs), the charts (data series read
back) and the exports (download events); records JavaScript errors and failed calls, one screenshot per tab.
    usage: pc_uickit_test.py <branch> <cshs> [out.json] [--shots <dir>]
Engine settings from BAW_HOST / BAW_USER / BAW_PASSWORD / BAW_STATE (tools/bawenv.py); BAW 26: the same command with BAW_HOST=https://<workflow-center-host>."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import asyncio, json, re, sys
from playwright.async_api import async_playwright
import util_ui as u

args = [a for a in sys.argv[1:] if not a.startswith('--')]
BRANCH, CSHS = args[0], args[1]; OUT = args[2] if len(args) > 2 else 'uickit_test.json'
SHOTS = sys.argv[sys.argv.index('--shots') + 1] if '--shots' in sys.argv else _os.path.join(_os.path.dirname(_os.path.abspath(OUT)), 'uickit_shots')

VIS = "const vis=e=>{ const r=e.getBoundingClientRect(); return r.width>0 && r.height>0 && !e.closest('.tab-hidden'); };"

async def main():
    rep = u.Recorder()
    async with async_playwright() as p:
        b, ui = await u.open_dashboard(p, BRANCH, CSHS, SHOTS)
        pg, coach = ui.pg, ui.coach
        svc_calls = []   # the chart / table / select controls call POST /rest/bpm/wle/v1/service/<flow id> (not the coachflow endpoint util_ui records)
        pg.on('response', lambda r: svc_calls.append(f'{r.status} {r.url.split("/service/")[1][:36]}') if '/rest/bpm/wle/v1/service/' in r.url else None)
        # the kit dashboard has one page-level status line: document-wide helpers (buttons inside hidden tab panes are ignored)
        async def click(label, wait=2500):
            ok = await coach.evaluate("([l]) => { " + VIS + " const b=Array.from(document.querySelectorAll('button')).filter(e=>vis(e) && !e.closest('.modal') && e.innerText.trim()===l)[0]; if(!b) return false; b.click(); return true; }", [label])
            await pg.wait_for_timeout(wait); return ok
        async def status(): return await coach.evaluate("(document.querySelector('[data-viewid=\"StatusLine\"]') || {innerText: ''}).innerText.trim()")
        async def js(expr): return await coach.evaluate(expr)
        async def shot(name): await pg.screenshot(path=f'{SHOTS}/{name}.png', full_page=True)
        rep.rec('open', 'coach frame found', coach is not None)
        header = await js("document.body.innerText.slice(0, 300)")
        rep.rec('open', 'header from UK Init (env var appTitle, user name)', 'UI Controls Kit' in header and u.bawenv.USER in header, header[:100])
        tabs = await js("Array.from(document.querySelectorAll('a[id^=\"tabs-MainTabs-tab-text\"]')).map(e=>e.innerText.trim())")
        rep.rec('open', 'six family tabs', tabs == ['Inputs', 'Display', 'Structure', 'Events', 'Charts', 'Data'], str(tabs))

        # ---- Inputs
        await ui.tab('Inputs'); await shot('01-inputs-start')
        await click('Read values', 4000); st = await status()
        rep.rec('inputs', 'Read values (getters) shows the UK Init defaults (amount 1234.5, choice B, tag alpha, switch true, slider 40)',
                'amount=1234.5' in st and 'choice=B' in st and '"alpha"' in st and 'switch=true' in st and 'slider=40' in st, st[:400])
        rep.rec('inputs', 'bound values echoed by UK Echo Form (Service Call with inputData tw.local.form)', '|| bound:' in st and 'radioValue=yes' in st and 'tags=alpha' in st, st[st.find('|| bound'):][:300])
        rep.rec('inputs', 'rich text from the Text Editor binding', 'rich=Rich text from UK Init' in st and 'richText=Rich text from UK Init' in st, st[:300])
        rep.rec('inputs', 'Signature isEmpty() is false before clear() (the canvas counts as content)', 'signatureEmpty=false' in st, '')
        amount = coach.locator('[data-viewid="Amount"] input').last   # the Decimal re-formats on blur: type on the keyboard (locator.fill() is ignored)
        await amount.click(); await pg.keyboard.press('Control+A'); await pg.keyboard.type('99.75'); await pg.keyboard.press('Tab'); await pg.wait_for_timeout(400)
        await ui.fill('Phone', '5551234567'); await ui.fill('Pwd', 'secret1'); await ui.fill('Ta', 'gam')
        await ui.check('Choice', 'C')
        try: await coach.locator('[data-viewid="Tags"] select').select_option(['alpha', 'beta'], timeout=8000); await pg.wait_for_timeout(400)
        except Exception as e: print('multi select', str(e)[:80])
        # radio buttons: click the "No" input
        await coach.evaluate("() => { const e=document.querySelector('[data-viewid=\"RbNo\"] input'); if(e) e.click(); }")
        # switch: click the toggle; slider: set through the control API
        await coach.evaluate("() => { const e=document.querySelector('[data-viewid=\"Sw\"] input'); if(e) e.click(); }")
        await coach.evaluate("page.ui.get('Sl').setValue(65)")   # noUiSlider: no input element to type into, the control API writes the binding
        await pg.wait_for_timeout(600)
        lookup = await coach.evaluate("() => { const s=document.querySelector('[data-viewid=\"Lookup\"] select'); return s ? Array.from(s.options).map(o=>o.value+'='+o.text) : null; }")
        rep.rec('inputs', 'service-fed Single Select has the three regions from UK Lookup Items', bool(lookup) and any('EMEA' in o for o in lookup), str(lookup))
        await ui.select('Lookup', 'APAC')
        await click('Read values', 4000); st = await status(); await shot('02-inputs-filled')
        bound = st[st.find('|| bound'):]
        rep.rec('inputs', 'Decimal binding took 99.75 (getter and bound)', 'amount=99.75' in st and 'amount=99.75' in bound, st[:200])
        rep.rec('inputs', 'Masked Text binding keeps the mask literals', 'phone=(555) 123-4567' in bound, bound[:300])
        rep.rec('inputs', 'Radio Button Group binding C', 'choice=C' in bound, '')
        rep.rec('inputs', 'Multi Select binding holds alpha + beta', 'tags=alpha+beta' in bound, bound[bound.find('tags='):bound.find('tags=') + 20])
        rep.rec('inputs', 'single Radio Button wrote valueWhenSelected no', 'radioValue=no' in bound, '')
        rep.rec('inputs', 'Switch toggled to false', 'switchOn=false' in bound, '')
        rep.rec('inputs', 'Slider setValue(65) reached the binding', 'slider=65' in bound, bound[bound.find('slider='):bound.find('slider=') + 12])
        rep.rec('inputs', 'Password length 7', 'passwordLength=7' in bound, '')
        rep.rec('inputs', 'Type Ahead binding gam', 'typeAhead=gam' in bound, '')
        rep.rec('inputs', 'service Single Select binding APAC', 'lookup=APAC' in bound, '')
        rep.rec('inputs', 'Date Time Picker / Date Picker bindings hold dates', 'when=20' in bound and 'when2=20' in bound, bound[bound.find('when='):bound.find('when=') + 40])
        await click('Clear signature'); st = await status(); rep.rec('inputs', 'Signature clear() / isEmpty()', 'signature cleared, empty=true' in st, st[:100])

        # ---- Display
        await ui.tab('Display'); await shot('03-display')
        await click('Read values', 4000); st = await status()
        rep.rec('display', 'Read values: progress 30 (bound), note / badge / reader / tooltip texts', 'progress=30' in st and 'bar=30' in st and 'note=Notes accept' in st and 'badge=NEW' in st and 'expanded=false' in st and 'tooltip=Type any value' in st, st[:400])
        img = await js("(function(){ const i=document.querySelector('[data-viewid=\"Logo\"] img'); return i ? {src: i.getAttribute('src'), w: i.naturalWidth, h: i.naturalHeight} : null; })()")
        rep.rec('display', 'Image shows the web file of the app (natural size 96x32)', bool(img) and img.get('w') == 96 and img.get('h') == 32, str(img))
        await click('Add 10 %'); st = await status(); rep.rec('display', 'Progress Bar setProgress / getProgress', 'progress now 40' in st, st[:80])
        await click('Set status'); st = await status(); rep.rec('display', 'Status Box setStatusText', 'status box set' in st, st[:80])
        sbox = await js("(document.querySelector('[data-viewid=\"Sbox\"]') || {innerText:''}).innerText")
        rep.rec('display', 'status strip text visible (setStatusText + setStatusVisible)', 'saved at' in sbox, sbox[:80])
        more = await coach.evaluate("() => { const a=Array.from(document.querySelectorAll('[data-viewid=\"Reader\"] a')).filter(e=>/more/i.test(e.innerText))[0]; if(a){ a.click(); return true; } return false; }")
        await pg.wait_for_timeout(500); await click('Read values', 4000); st = await status()
        rep.rec('display', 'Text Reader read more link expands', more and 'expanded=true' in st, st[st.find('reader='):st.find('reader=') + 40])
        badges = await js("Array.from(document.querySelectorAll('[data-viewid^=\"Badge\"]')).map(e=>e.innerText.trim())")
        rep.rec('display', 'three badges rendered (badge / label / tag shapes)', badges == ['NEW', 'label', 'tag'], str(badges))
        await shot('04-display-after')

        # ---- Structure
        await ui.tab('Structure'); await shot('05-structure')
        await click('Read values', 4000); st = await status()
        rep.rec('structure', 'Read values: stack pane null before any switch, panel 1 open / panel 2 closed, split 2 panes, deferred not loaded, variant hello', 'stack pane=null' in st and 'expanded=true/false' in st and 'split panes=2' in st and 'deferred loaded=false' in st and 'variant=hello' in st, st[:400])
        rep.rec('structure', 'Responsive Sensor reports the active box factor', 'sensor=wide' in st, st[st.find('sensor='):st.find('sensor=') + 60])
        await click('Pane 1'); st = await status(); rep.rec('structure', 'Stack setCurrentPane(1)', 'stack pane 1' in st, st[:60])
        visible1 = await js("(function(){ const e=document.querySelector('[data-viewid=\"StackT1\"]'); return e && e.getBoundingClientRect().height>0; })()")
        rep.rec('structure', 'stack pane 1 content visible', bool(visible1), '')
        await coach.evaluate("() => { const h=document.querySelector('[data-viewid=\"Coll2\"] .accordion-toggle'); if(h) h.click(); }"); await pg.wait_for_timeout(800)
        st = await status(); rep.rec('structure', 'Collapsible Panel group: opening panel 2 fires On expand (and closes panel 1)', 'panel 2 expanded' in st, st[:80])
        await click('Read values', 4000); st = await status(); rep.rec('structure', 'panel group state after the click: 1 closed, 2 open', 'expanded=false/true' in st, st[st.find('collapsible'):st.find('collapsible') + 40])
        await ui.fill('SearchText', 'needle')
        igb = await coach.evaluate("() => { const b=document.querySelector('[data-viewid=\"Ig\"] button, [data-viewid=\"Ig\"] .input-group-btn, [data-viewid=\"Ig\"] .input-group-addon'); if(b){ b.click(); return b.outerHTML.slice(0,120); } return null; }"); await pg.wait_for_timeout(600)
        st = await status(); rep.rec('structure', 'Input Group button click reads the text', 'search clicked: needle' in st, st[:80] + ' / ' + str(igb))
        await click('Read values', 4000); st = await status(); rep.rec('structure', 'Input Group text reached the bound variable', 'searchText=needle' in st, st[st.find('searchText='):st.find('searchText=') + 20])
        await click('Load deferred section'); st = await status(); rep.rec('structure', 'Deferred Section lazyLoad + On lazy-loaded', 'deferred section loaded: true' in st, st[:80])
        deferred_text = await js("(document.querySelector('[data-viewid=\"DeferText\"]') || {innerText:''}).innerText")
        rep.rec('structure', 'deferred content rendered', 'Deferred content is now loaded' in deferred_text, deferred_text[:60])
        await click('Actions (popup menu)', 800)
        menu = await coach.evaluate("() => { const m=document.querySelector('.dropdown-menu.open'); if(!m) return 'no open menu'; const it=Array.from(m.querySelectorAll('li, a, span, div')).filter(e=>e.textContent.trim()==='Delete').pop(); if(it){ it.click(); return true; } return 'no item: ' + m.outerHTML.slice(0, 400); }"); await pg.wait_for_timeout(600)
        st = await status(); rep.rec('structure', 'Popup Menu opened by setMenuVisible (rendered outside the view), item click delivers the command', menu is True and 'menu command: delete' in st, st[:80] + ' / ' + str(menu))
        grid = await js("Array.from(document.querySelectorAll('[data-viewid=\"Grid\"] td')).map(e=>e.innerText.trim()).filter(x=>x)")
        rep.rec('structure', 'Table Layout renders the 2x2 cells', grid == ['cell 0,0', 'cell 0,1', 'cell 1,0', 'cell 1,1'], str(grid))
        variant = await js("(function(){ const v=document.querySelector('[data-viewid=\"Var1\"]'); return v ? {text: !!v.querySelector('[data-viewid=\"VarText\"] input'), value: (v.querySelector('input')||{}).value} : null; })()")
        rep.rec('structure', 'Variant shows the String child for a String binding', bool(variant) and variant.get('text') and variant.get('value') == 'hello', str(variant))
        await shot('06-structure-after')

        # ---- Events
        await ui.tab('Events'); await shot('07-events')
        await click('Read values', 4000); st = await status()
        rep.rec('events', 'Read values: config parameter, Data value, exit safeguard off, 3 crumbs, device info', 'config mode=demo' in st and 'data=initial' in st and 'exit challenged=false' in st and 'crumbs=3' in st and 'browserName' in st, st[:400])
        await click('Append alert'); alert_text = await js("(document.querySelector('[data-viewid=\"AlertArea\"]') || {innerText:''}).innerText")
        rep.rec('events', 'Alerts appendAlert shows the alert', 'The alert area shows this message' in alert_text, alert_text[:80])
        await click('Modal alert', 1200); m = await ui.modal()
        rep.rec('events', 'Modal Alert opens with title, text and the custom button', bool(m) and 'Hello from the Modal Alert' in m['text'] and 'Got it' in m['buttons'], json.dumps(m)[:200] if m else 'no modal')
        if m: await ui.modal_click('Got it', 800)
        st = await status(); rep.rec('events', 'Modal Alert On close fired', 'modal alert closed' in st, st[:60])
        await click('Publish event'); st = await status()
        rep.rec('events', 'Event Subscription received the published payload (handler runs synchronously inside publishEvent)', 'event received' in st and '"n":42' in st.replace(' ', ''), st[:120])
        await click('Start timer (1.5 s)', 2600); st = await status(); rep.rec('events', 'Timer On timeout after start()', 'timer fired: ticks=1' in st, st[:60])
        await click('Toggle exit safeguard'); st = await status(); rep.rec('events', 'Exit Safeguard setExitChallenged(true)', 'exit challenged: true' in st, st[:60])
        await click('Toggle exit safeguard'); st = await status(); rep.rec('events', 'Exit Safeguard back to false', 'exit challenged: false' in st, st[:60])
        await click('Set data'); st = await status(); rep.rec('events', 'Data control setValue / getValue', 'data set: set at' in st, st[:60])
        await click('Read values', 4000); st = await status(); rep.rec('events', 'Data control wrote the bound variable (echo)', 'dataValue=set at' in st, st[st.find('dataValue='):st.find('dataValue=') + 40])
        await click('Request location', 3000); st = await status(); rep.rec('events', 'Geo Location answers (location or a permission / provider error)', 'location:' in st or 'location error' in st, st[:120])
        await click('Append crumb'); st = await status(); rep.rec('events', 'Breadcrumbs appendItem', 'crumbs: 4' in st, st[:60])
        clicked = await coach.evaluate("() => { const a=Array.from(document.querySelectorAll('[data-viewid=\"Crumbs\"] a, [data-viewid=\"Crumbs\"] li')).filter(e=>/Requests/.test(e.innerText))[0]; if(a){ a.click(); return true; } return false; }"); await pg.wait_for_timeout(600)
        st = await status(); rep.rec('events', 'Breadcrumbs On item click gives label + data (trail kept by return false)', clicked and 'crumb clicked: Requests data=requests' in st, st[:100])
        await shot('08-events-after')

        # ---- Charts
        await ui.tab('Charts', 3000); await click('Redraw charts', 1500); await shot('09-charts')
        await click('Read values'); st = await status()
        rep.rec('charts', 'variable-fed charts (bar / pie / area) hold the 5-point series from UK Init', 'bar=Tasks per day:5' in st and 'pie=Tasks per day:5' in st and 'area=Tasks per day:5' in st, st[:300])
        rep.rec('charts', 'service-fed charts (line / donut / step) hold the series from UK Chart Data', 'line=Instances per week:5' in st and 'donut=Instances per week:5' in st and 'step=Instances per week:5' in st, st[:300])
        svg = await js("Array.from(document.querySelectorAll('[data-viewid^=\"Chart\"]:not([data-viewid=\"ChartsTab\"])')).map(e=>e.getAttribute('data-viewid')+':'+e.querySelectorAll('svg, canvas').length+':'+Math.round(e.getBoundingClientRect().width))")
        rep.rec('charts', 'every chart rendered an svg / canvas with a width', all(int(x.split(':')[1]) > 0 and int(x.split(':')[2]) > 100 for x in svg) and len(svg) == 7, str(svg))
        rep.rec('charts', 'chart / table / lookup flows called through POST /rest/bpm/wle/v1/service/<id> and answered 200', all(c.startswith('200 ') for c in svc_calls) and len(svc_calls) >= 6, '; '.join(svc_calls)[:300])
        await click('Refresh service charts', 3000); st = await status(); rep.rec('charts', 'refresh() of the service charts', 'service charts refreshed' in st, st[:60])

        # ---- Data
        await ui.tab('Data'); await shot('10-data')
        rows = await ui.rows('Rows'); rep.rec('data', 'Table shows the 6 rows of UK Init', len(rows) == 6 and 'Alpha' in rows[0], str(rows)[:200])
        svc_rows = await ui.rows('SvcRows'); rep.rec('data', 'Service Data Table loaded 5 rows from UK Table Data at start', len(svc_rows) == 5, str(svc_rows)[:200])
        await ui.select_row('Rows', 1); await click('Read values', 4000); st = await status()
        rep.rec('data', 'Read values: 6 rows, selected record Beta, 5 service rows', 'rows=6' in st and '"Beta"' in st and 'service rows=5' in st, st[:300])
        await ui.fill('Query', 'client'); await click('Refresh service table', 3000); svc_rows = await ui.rows('SvcRows')
        rep.rec('data', 'Service Data Table refresh(true) with query data filters to the 2 client rows', len(svc_rows) == 2 and all('Client' in r for r in svc_rows), str(svc_rows)[:200])
        for label, name, kind in [('Export bound rows (CSV)', 'uickit-rows', 'bound csv'), ('Export bound rows (XLSX)', 'uickit-rows', 'bound xlsx'), ('Export the table above (CSV, tableName)', 'uickit-table', 'table csv')]:
            try:
                async with pg.expect_download(timeout=8000) as dl:
                    await click(label, 500)
                d = await dl.value; path = await d.path(); size = _os.path.getsize(path) if path else 0
                body = open(path, 'rb').read(400) if path and kind.endswith('csv') else b''
                rep.rec('data', f'Data Export {kind}: download {d.suggested_filename} ({size} bytes)', size > 0 and name in d.suggested_filename and (kind.endswith('xlsx') or b'Alpha' in body), (body[:120].decode('utf-8', 'replace') if body else d.suggested_filename))
            except Exception as e: rep.rec('data', f'Data Export {kind}: download', False, str(e)[:120])
        await shot('11-data-after')

        rep.rec('errors', 'no JavaScript errors', not ui.errors, '; '.join(ui.errors)[:400])
        failed = [c for c in ui.calls if not c.startswith('200 ') and not c.startswith('304 ')]
        rep.rec('errors', 'no failed HTTP calls', not failed, '; '.join(failed)[:300])
        await b.close()
    json.dump(dict(checks=rep.items, errors=ui.errors, calls=ui.calls), open(OUT, 'w'), indent=1)
    print(rep.markdown('UI Controls Kit deep test')); print(rep.summary())
asyncio.run(main())
