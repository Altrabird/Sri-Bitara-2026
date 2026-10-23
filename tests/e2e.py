"""End-to-end test of index.html (demo mode + remote mode against tests/gas-mock.js).
Usage: python tests/e2e.py [path-to-awards.xlsx] [screenshot-dir]
The xlsx is optional and stays local — it is only read by the browser under test."""
import pathlib, subprocess, sys, time
from playwright.sync_api import sync_playwright, expect

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = (ROOT / 'index.html').as_uri()
DEMO_URL = URL + '?api=demo'
XLSX = sys.argv[1] if len(sys.argv) > 1 else None
SHOTS = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
PORT = 8787


def _png(w=8, h=6):
    import struct, zlib
    raw = b''.join(b'\x00' + bytes([200, 150, 60]) * w for _ in range(h))
    chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


IMG = {'name': 'foto.png', 'mimeType': 'image/png', 'buffer': _png()}
errors = []


def page_for(ctx, url):
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.on('console', lambda m: m.type == 'error' and 'drive.google.com' not in m.text and 'ERR_' not in m.text and errors.append(m.text))
    pg.on('dialog', lambda d: d.accept())
    pg.goto(url)
    # kad undangan: app is locked until the card is tapped, on every load
    expect(pg.locator('#invCard')).to_be_visible()
    pg.wait_for_timeout(400)
    assert pg.evaluate("document.querySelector('.app').inert"), 'app locked behind invitation'
    if SHOTS and not getattr(page_for, 'shot', False):
        page_for.shot = True
        pg.screenshot(path=str(SHOTS / 'invite-closed.png'))
        pg.click('#invCard', force=True); pg.wait_for_timeout(1700)
        pg.screenshot(path=str(SHOTS / 'invite-open.png'))
    else:
        pg.click('#invCard', force=True)
    pg.wait_for_selector('#invite', state='detached', timeout=6000)
    assert not pg.evaluate("document.querySelector('.app').inert")
    return pg


def shot(pg, name):
    if SHOTS:
        pg.screenshot(path=str(SHOTS / f'{name}.png'))


def unlock(pg, pin):
    pg.click('.nav[data-v=tetapan]')
    pg.fill('#pinIn', pin)
    pg.press('#pinIn', 'Enter')
    expect(pg.locator('#admin')).to_be_visible(timeout=8000)


def import_xlsx(pg):
    pg.click('.nav[data-v=tetapan]')
    pg.click('#admin .chip[data-t=import]')
    pg.set_input_files('#xlsx', XLSX)
    expect(pg.locator('#impSave')).to_be_visible(timeout=20000)
    rows = pg.eval_on_selector_all('#impOut tbody tr', 'rs=>rs.map(r=>[r.cells[0].firstChild.textContent,r.cells[1].querySelector("select").value,+r.cells[2].textContent])')
    pg.click('#impSave')
    pg.wait_for_function("!document.querySelector('#impSave') && D.penerima.length>100", timeout=20000)
    return rows


def common_flow(pg, tag):
    # every view renders
    for v in ['anugerah', 'ajk', 'tentatif', 'galeri', 'dashboard']:
        pg.click(f'.nav[data-v={v}]')
        pg.wait_for_timeout(700)
        shot(pg, f'{tag}-{v}')
    assert pg.locator('#ajkGrid .jk').count() == 24 or pg.evaluate('D.ajk.length') == 24


with sync_playwright() as p:
    b = p.chromium.launch()

    # ---------- A: demo mode ----------
    ctx = b.new_context(viewport={'width': 1440, 'height': 900})
    pg = page_for(ctx, DEMO_URL)
    assert 'Mod demo' in pg.inner_text('#sync')
    assert pg.evaluate('D.anugerah.length') == 23
    if (ROOT / 'audio' / 'muzik-latar.mp3').exists():
        assert not pg.evaluate('bgm.paused'), 'music plays after the card is opened'
        pg.click('#muteBtn')
        pg.wait_for_function('bgm.paused')
        pg.click('#muteBtn')
    common_flow(pg, 'demo')
    unlock(pg, '123456')
    shot(pg, 'demo-tetapan')
    if XLSX:
        rows = import_xlsx(pg)
        total = sum(r[2] for r in rows)
        print(f'import: {len(rows)} awards, {total} recipients')
        for r in rows:
            print(f'   {r[1]:>2}  {r[2]:>4}  {r[0]}')
        assert len(rows) >= 20 and total > 600
        assert pg.evaluate('D.penerima.every(p=>p.nama && p.aid)')
        # no IC/address sheet leaked
        assert not pg.evaluate("D.penerima.some(p=>/\\d{6}/.test(p.nama+p.kelas))")
        no_kelas = pg.evaluate("D.penerima.filter(p=>!p.kelas).length")
        print('recipients without kelas:', no_kelas)
        # drawer + status toggle
        pg.click('.nav[data-v=anugerah]')
        pg.locator('#awGrid .aw').first.click()
        btn = pg.locator('#drawer .tg[data-id]').first
        btn.click()
        expect(pg.locator('#drawer .tg[data-id]').first).to_have_text('✓ Diterima')
        shot(pg, 'demo-drawer')
        # mod pentas: title → name → auto-mark
        pg.click('#toStage')
        expect(pg.locator('#stage')).to_be_visible()
        expect(pg.locator('#stSlide .title')).to_be_visible()
        pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(1600)
        shot(pg, 'demo-pentas')
        second = pg.evaluate('slides()[2].p.id')
        pg.keyboard.press('ArrowRight'); pg.keyboard.press('ArrowRight'); pg.wait_for_timeout(300)
        assert pg.evaluate(f'D.penerima.find(p=>p.id==="{second}").status') == 'Diterima', 'auto-mark on advance'
        pg.keyboard.press('Escape')
        pg.keyboard.press('Escape')
        # Senarai Murid: pupils with more than one award
        pg.click('.nav[data-v=anugerah]')
        pg.click('#awMode [data-m=murid]')
        expect(pg.locator('#awList .ms').first).to_be_visible()
        kpis = pg.eval_on_selector_all('#awList .ms-kpi .n', 'e=>e.map(x=>x.textContent)')
        by_name = pg.evaluate("(()=>{const c={};D.penerima.forEach(p=>(c[p.nama]=c[p.nama]||new Set()).add(p.aid));const v=Object.values(c);return [v.length,v.filter(s=>s.size>1).length]})()")
        print('senarai murid KPI:', kpis, '| by name only:', by_name)
        assert [int(kpis[0]), int(kpis[1])] == by_name, 'one entry per pupil name'
        assert int(kpis[1]) == pg.locator('#awList .ms').count() > 0
        assert pg.evaluate("D.penerima.some(p=>D.anugerah.find(a=>a.id===p.aid).nama==='Anugerah Duta Sahsiah'&&p.kelas.startsWith('5 '))"), 'Duta Sahsiah Tahun 5 inferred'
        assert all(int(x) >= 2 for x in pg.eval_on_selector_all('#awList .ms-c b', 'e=>e.map(x=>x.textContent)'))
        pg.fill('#awQ', 'alex daniel')
        row = pg.locator('#awList .ms').first
        expect(row).to_contain_text('Bahasa Melayu')
        expect(row).to_contain_text('Pendidikan Moral')
        pg.fill('#awQ', '')
        shot(pg, 'demo-senarai-murid')
        pg.uncheck('#msMulti')
        assert pg.locator('#awList .ms').count() == int(kpis[0])
        pg.locator('#awList .b').first.click()
        expect(pg.locator('#drawer')).to_have_class('drawer on')
        pg.keyboard.press('Escape')
        pg.click('#awMode [data-m=kad]')
    # tentatif live control
    pg.click('.nav[data-v=tentatif]')
    pg.locator('#tl .ti').nth(2).locator('button').click()
    pg.wait_for_timeout(300)
    assert pg.evaluate('D.settings.now') == 3  # row 0 is the day heading
    expect(pg.locator('#tl .ti.live')).to_have_count(1)
    # gallery upload / lightbox / delete
    pg.click('.nav[data-v=galeri]')
    pg.set_input_files('#uplFile', files=[IMG])
    expect(pg.locator('#gal .ph')).to_have_count(1, timeout=8000)
    pg.locator('#gal .open').first.click()
    expect(pg.locator('#lb')).to_have_class('lb on')
    pg.keyboard.press('Escape')
    pg.locator('#gal .del').first.click()
    expect(pg.locator('#gal .ph')).to_have_count(0)
    # row editor: add AJK and save
    pg.click('.nav[data-v=tetapan]')
    pg.click('#admin .chip[data-t=ajk]')
    pg.click('#reAjk [data-a=add]')
    pg.locator('#reAjk .re-row[data-i]').last.locator('input').fill('JK Ujian')
    pg.locator('#reAjk .re-row[data-i]').last.locator('textarea').first.fill('Cikgu Satu (K)\nCikgu Dua')
    pg.click('#reAjk [data-a=save]')
    pg.wait_for_function('D.ajk.length===25')
    # settings: date + public names off by default → lock hides names
    pg.click('#admin .chip[data-t=majlis]')
    pg.fill('#sTarikh', '2026-12-01')
    pg.click('#sSave')
    pg.wait_for_function('D.settings.tarikh==="2026-12-01"')
    pg.click('#admin .chip[data-t=sistem]')
    pg.locator('#admin .setp.on button', has_text='Kunci').click()
    pg.wait_for_timeout(500)
    assert not pg.evaluate('document.body.classList.contains("admin")')
    if XLSX:
        pg.click('.nav[data-v=anugerah]')
        pg.locator('#awGrid .aw').first.click()
        expect(pg.locator('#drawer .body')).to_contain_text('akan diumumkan')
        pg.keyboard.press('Escape')
        pg.click('#awMode [data-m=murid]')
        expect(pg.locator('#awList')).to_contain_text('akan diumumkan')
        pg.click('#awMode [data-m=kad]')
    ctx.close()

    # mobile layout check
    ctx = b.new_context(viewport={'width': 390, 'height': 844})
    pg = page_for(ctx, DEMO_URL)
    shot(pg, 'mobile-dashboard')
    assert not pg.evaluate('document.documentElement.scrollWidth>innerWidth'), 'no horizontal scroll'
    for v in ['anugerah', 'ajk', 'tentatif', 'galeri', 'tetapan']:
        pg.click(f'.nav[data-v={v}]'); pg.wait_for_timeout(500)
        assert not pg.evaluate('document.documentElement.scrollWidth>innerWidth'), f'hscroll on {v}'
    shot(pg, 'mobile-tetapan')
    ctx.close()

    # ---------- B: remote mode against the real Code.gs ----------
    srv = subprocess.Popen(['node', str(ROOT / 'tests' / 'gas-mock.js'), str(PORT)], stdout=subprocess.PIPE)
    srv.stdout.readline()
    try:
        ctx = b.new_context(viewport={'width': 1440, 'height': 900})
        pg = page_for(ctx, URL + f'?api=http://localhost:{PORT}/exec')
        expect(pg.locator('#sync')).to_contain_text('Langsung', timeout=8000)
        assert pg.evaluate('D.anugerah.length') == 0
        # wrong PIN
        pg.click('.nav[data-v=tetapan]')
        pg.fill('#pinIn', '111111'); pg.press('#pinIn', 'Enter')
        expect(pg.locator('#pinMsg')).to_have_text('PIN salah', timeout=8000)
        pg.wait_for_timeout(600)
        pg.fill('#pinIn', '246810'); pg.press('#pinIn', 'Enter')
        expect(pg.locator('#admin')).to_be_visible(timeout=8000)
        pg.wait_for_function('D.anugerah.length===23 && D.ajk.length===24', timeout=15000)  # seeded via confirm()
        # add recipients: pick class, tick pupils from the Hadir roster, plus one manual name
        pg.click('.nav[data-v=anugerah]')
        pg.locator('#awGrid .aw').nth(5).click()
        expect(pg.locator('#adKls')).to_be_visible(timeout=8000)
        pg.select_option('#adKls', '4 KREATIF')
        expect(pg.locator('#addp .st')).to_have_count(3)
        pg.locator('#addp .st input').nth(0).check()
        pg.locator('#addp .st input').nth(2).check()
        expect(pg.locator('#adN')).to_have_text(' (2)')
        pg.fill('#adMan', 'murid baharu')
        pg.click('#adGo')
        expect(pg.locator('#drawer .rcp')).to_have_count(3, timeout=8000)
        expect(pg.locator('#addp .st.have')).to_have_count(2)
        assert pg.evaluate("D.penerima.every(p=>p.kelas==='4 KREATIF'&&p.tahun==='4')")
        assert pg.evaluate("D.penerima.some(p=>p.nama==='MURID BAHARU')")
        shot(pg, 'remote-add')
        pg.locator('#drawer .del-p').first.click()
        expect(pg.locator('#drawer .rcp')).to_have_count(2, timeout=8000)
        pg.keyboard.press('Escape')
        if XLSX:
            import_xlsx(pg)
            n = pg.evaluate('D.penerima.length')
            pg.click('#admin .chip[data-t=majlis]')
            pg.check('#sShow')
            pg.click('#sSave')
            pg.wait_for_function('D.settings.showNames===true')
        pg.click('.nav[data-v=galeri]')
        pg.set_input_files('#uplFile', files=[IMG])
        expect(pg.locator('#gal .ph')).to_have_count(1, timeout=8000)
        assert 'drive.google.com/thumbnail' in pg.get_attribute('#gal img', 'src')
        pg.evaluate('lockAdmin()')
        pg.wait_for_timeout(1500)
        if XLSX:
            got = pg.evaluate('D.penerima && D.penerima.length'); assert got == n, f'public sees names when showNames on: {got} vs {n}'
        # a second visitor gets the same live data
        pg2 = page_for(ctx, URL)
        expect(pg2.locator('#sync')).to_contain_text('Langsung', timeout=8000)
        assert pg2.evaluate('D.galeri.length') == 1
        shot(pg2, 'remote-dashboard')
        ctx.close()
    finally:
        srv.terminate()
    b.close()

print('ERRORS:', errors)
assert not errors, errors
print('e2e: all tests passed')
