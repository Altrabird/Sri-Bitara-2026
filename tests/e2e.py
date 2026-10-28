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
    pg.click('#ttDone')  # marks the majlis selesai (used by the Laporan)
    pg.wait_for_function('D.settings.now===D.tentatif.length')
    expect(pg.locator('#tl')).to_contain_text('Majlis telah ditanda selesai')
    pg.locator('#tl button', has_text='Set semula').click()
    pg.wait_for_function('D.settings.now===-1')
    # gallery upload / lightbox / delete
    pg.click('.nav[data-v=galeri]')
    pg.set_input_files('#uplFile', files=[IMG])
    expect(pg.locator('#gal .ph')).to_have_count(1, timeout=8000)
    pg.locator('#gal .open').first.click()
    expect(pg.locator('#lb')).to_have_class('lb on')
    pg.keyboard.press('Escape')
    # dashboard Galeri Foto card shows it and opens the viewer
    pg.click('.nav[data-v=dashboard]')
    expect(pg.locator('#v-dashboard .dgal .open')).to_have_count(1)
    shot(pg, 'demo-dashboard-galeri')
    pg.locator('#v-dashboard .dgal .open').first.click()
    expect(pg.locator('#lb')).to_have_class('lb on')
    pg.keyboard.press('Escape')
    pg.click('.nav[data-v=galeri]')
    pg.locator('#gal .del').first.click()
    expect(pg.locator('#gal .ph')).to_have_count(0)
    # row editor: add AJK and save
    pg.click('.nav[data-v=tetapan]')
    pg.click('#admin .chip[data-t=ajk]')
    pg.click('#reAjk [data-a=add]')
    pg.locator('#reAjk .re-row[data-i]').last.locator('input').fill('JK Ujian')
    pg.locator('#reAjk .re-row[data-i]').last.locator('textarea').first.fill('Cikgu Satu (K)\nCikgu Dua')
    pg.evaluate('refresh(true)'); pg.wait_for_timeout(300)  # the 15 s admin poll must not wipe unsaved edits
    assert pg.locator('#reAjk .re-row[data-i]').last.locator('input').input_value() == 'JK Ujian', 'poll reset unsaved AJK edits'
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
        # bulk paste: comma / Excel tab / numbered lines; class anywhere; no class and no class chosen → skipped
        got = pg.evaluate(r"""parseBulk('Ahmad bin Ali, 6 inovatif\n1\tSITI AISYAH BINTI OMAR\t5 KREATIF\n2. Lim Wei - 4 Kritis\nTIADA KELAS SAMA SEKALI\n\n6\tPATRIOTIK\tCHONG MEI LING','')""")
        assert got == [{'nama': 'AHMAD BIN ALI', 'kelas': '6 INOVATIF'}, {'nama': 'SITI AISYAH BINTI OMAR', 'kelas': '5 KREATIF'},
                       {'nama': 'LIM WEI', 'kelas': '4 KRITIS'}, {'nama': 'TIADA KELAS SAMA SEKALI', 'kelas': ''},
                       {'nama': 'CHONG MEI LING', 'kelas': '6 PATRIOTIK'}], got
        assert pg.evaluate("parseBulk('ALI BIN ABU','3 KREATIF')") == [{'nama': 'ALI BIN ABU', 'kelas': '3 KREATIF'}], 'default class'
        pg.locator('#awGrid .aw').nth(6).click()
        expect(pg.locator('#adKls')).to_be_visible(timeout=8000)
        pg.select_option('#adKls', '')  # no default class, so the class-less line is skipped
        pg.click('#addp .bulk summary')
        pg.fill('#adBulk', 'Ahmad bin Ali, 6 inovatif\n1\tSITI AISYAH BINTI OMAR\t5 KREATIF\nTIADA KELAS SAMA SEKALI')
        expect(pg.locator('#adBulkInfo')).to_contain_text('2 murid')
        expect(pg.locator('#adBulkInfo')).to_contain_text('1 baris tiada kelas')
        shot(pg, 'remote-bulk')
        pg.click('#adBulkGo')
        expect(pg.locator('#drawer .rcp')).to_have_count(2, timeout=8000)
        assert pg.evaluate("D.penerima.filter(p=>p.aid===D.anugerah[6].id).map(p=>p.nama+'|'+p.kelas+'|'+p.tahun).sort().join()") == 'AHMAD BIN ALI|6 INOVATIF|6,SITI AISYAH BINTI OMAR|5 KREATIF|5'
        expect(pg.locator('#adBulk')).to_have_value('')
        pg.fill('#adBulk', 'AHMAD BIN ALI, 6 INOVATIF')  # already there → skipped, not duplicated
        pg.click('#adBulkGo')
        expect(pg.locator('#toast')).to_contain_text('sudah ada', timeout=8000)
        expect(pg.locator('#drawer .rcp')).to_have_count(2)
        pg.keyboard.press('Escape')
        # sasaran: target 5 on that award → card shows 2 / 5; others stay unlimited
        pg.click('.nav[data-v=tetapan]')
        pg.click('#admin .chip[data-t=anugerah]')
        pg.locator('#reAw .re-row[data-i] [data-k=sasaran]').nth(5).fill('5')
        pg.click('#reAw [data-a=save]')
        pg.wait_for_function("D.anugerah[5].sasaran==='5'", timeout=8000)
        pg.click('.nav[data-v=anugerah]')
        expect(pg.locator('#awGrid .aw').nth(5)).to_contain_text('2 / 5 penerima')
        expect(pg.locator('#awGrid .aw .prog.t')).to_have_count(1)
        # laporan builds from live data
        pg.click('.nav[data-v=tetapan]')
        pg.click('#admin .chip[data-t=laporan]')
        lap = pg.locator('#admin .lap')
        expect(lap).to_contain_text('SKOR KEJAYAAN KESELURUHAN')
        expect(lap).to_contain_text('Laporan sementara')
        expect(lap).to_contain_text('Pencapaian sasaran penerima')
        expect(lap).to_contain_text('2 / 5 (1 anugerah bersasaran)')
        expect(lap).to_contain_text('TUAN HJ YUSOFF BIN HJ AWANG YAHYA')  # setiausaha from AJK Induk
        shot(pg, 'remote-laporan')
        # surat jemputan: a pupil with awards in two categories gets ONE letter listing both
        pg.evaluate("call('addPenerima',{rows:[{id:'rx1',aid:D.anugerah[12].id,kelas:'4 KREATIF',tahun:'4',nama:'MURID BAHARU',catatan:''}]},{quiet:true})")
        pg.wait_for_function("D.penerima.filter(p=>p.nama==='MURID BAHARU').length===2", timeout=8000)
        names = pg.evaluate('new Set(D.penerima.map(p=>p.nama)).size')
        surat = pg.evaluate('suratHTML()')
        assert surat['n'] == names, (surat['n'], names)
        aw5, aw12 = pg.evaluate('[D.anugerah[5].nama, D.anugerah[12].nama]')
        letter = [x for x in surat['html'].split('class="pb"') if '<b>MURID BAHARU</b>' in x]
        assert len(letter) == 1 and aw5 in letter[0] and aw12 in letter[0] and '<b>2</b> anugerah' in letter[0], 'one letter, both awards'
        # downloads: per kategori, keseluruhan, surat
        pg.click('.nav[data-v=anugerah]')
        with pg.expect_download() as dl:
            pg.click('#awDl')
        assert dl.value.suggested_filename == 'Senarai-Penerima-Keseluruhan.doc'
        pg.click('#awCats .chip[data-c=K]')
        with pg.expect_download() as dl:
            pg.click('#awDl')
        assert dl.value.suggested_filename == 'Senarai-Penerima-Kurikulum.doc'
        assert aw5 in open(dl.value.path(), encoding='utf-8-sig').read()
        pg.click('#awCats .chip[data-c=ALL]')
        with pg.expect_download() as dl:
            pg.locator('#v-anugerah button', has_text='Surat jemputan').click()
        assert dl.value.suggested_filename == 'Surat-Jemputan-Penerima-Anugerah.doc'
        # same downloads as Excel / CSV
        pg.select_option('#dlFmt', 'xlsx')
        with pg.expect_download() as dl:
            pg.click('#awDl')
        assert dl.value.suggested_filename == 'Senarai-Penerima-Keseluruhan.xlsx'
        assert open(dl.value.path(), 'rb').read(2) == b'PK', 'real xlsx'
        pg.select_option('#dlFmt', 'csv')
        with pg.expect_download() as dl:
            pg.locator('#v-anugerah button', has_text='Surat jemputan').click()
        assert dl.value.suggested_filename == 'Surat-Jemputan-Senarai-Mail-Merge.csv'
        merge = open(dl.value.path(), encoding='utf-8-sig').read()
        row = [l for l in merge.splitlines() if '"MURID BAHARU"' in l]
        assert len(row) == 1 and aw5 in row[0] and aw12 in row[0] and '"2"' in row[0], 'one merge row, both awards'
        pg.select_option('#dlFmt', 'doc')
        pg.click('.nav[data-v=tetapan]')
        # foto AJK: names match files despite titles / Bt vs Binti; a photo that fails to load falls back to initials
        assert pg.evaluate("nameKey('En Harsidi Bin Junick (Penyelaras Program)')===nameKey('Harsidi Bin Junick') && nameKey('Pn. Kalsom Bt Tang')===nameKey('Kalsom Binti Tang')")
        pg.click('#admin .chip[data-t=ajk]')
        pg.fill('#sFoto', 'https://drive.google.com/drive/folders/tiada-folder?usp=sharing')
        pg.click('#sFotoSave')
        pg.wait_for_function("D.settings.fotoFolder==='tiada-folder'", timeout=8000)
        expect(pg.locator('#admin .setp.on')).to_contain_text('0 foto dijumpai')
        pg.evaluate("FOTO=new Map([[nameKey('Harsidi Bin Junick'),'tiada']])")
        pg.click('.nav[data-v=ajk]')
        expect(pg.locator('#ajkGrid .mem', has_text='Harsidi').locator('.av')).to_have_text('HJ', timeout=8000)
        # click the initials → pick a picture → drag a box → saved to Drive as "Harsidi Bin Junick.jpg"
        pg.locator('#ajkGrid .mem', has_text='Harsidi').locator('.av').click()
        expect(pg.locator('#snip')).to_have_class('lb on')
        expect(pg.locator('#snipT')).to_have_text('Harsidi Bin Junick')
        pg.set_input_files('#snipFile', files=[{'name': 'kumpulan.png', 'mimeType': 'image/png', 'buffer': _png(200, 160)}])
        expect(pg.locator('#snipSel')).to_be_visible()
        box = pg.locator('#snipImg').bounding_box()
        pg.mouse.move(box['x'] + 20, box['y'] + 20); pg.mouse.down(); pg.mouse.move(box['x'] + 120, box['y'] + 90, steps=8); pg.mouse.up()
        assert pg.evaluate('Math.round(SNIP.sel.s)') == 100, pg.evaluate('SNIP.sel')
        pg.click('#snipOk')
        pg.wait_for_function("D.fotoAjk.some(f=>f.n==='Harsidi Bin Junick') && !document.querySelector('#snip.on')", timeout=8000)
        assert pg.evaluate("D.settings.fotoFolder!=='tiada-folder'"), 'Foto AJK folder created when the set one is missing'
        assert 'drive.google.com/thumbnail' in pg.locator('#ajkGrid .mem', has_text='Harsidi').locator('.av img').get_attribute('src')
        shot(pg, 'remote-foto-ajk')
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
