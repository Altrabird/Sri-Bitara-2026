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
    b = p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])  # fake camera for the in-app photo camera

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
        btn = pg.locator('#drawer .tg[data-ids]').first
        btn.click()
        expect(pg.locator('#drawer .tg[data-ids]').first).to_have_text('✓ Diterima')
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
        # Senarai Murid: every pupil, or only those with more than one award
        pg.click('.nav[data-v=anugerah]')
        pg.click('#awMode [data-m=murid]')
        expect(pg.locator('#awList .ms').first).to_be_visible()
        kpis = pg.eval_on_selector_all('#awList .ms-kpi .n', 'e=>e.map(x=>x.textContent)')
        by_name = pg.evaluate("(()=>{const c={};D.penerima.forEach(p=>(c[p.nama]=c[p.nama]||new Set()).add(p.aid));const v=Object.values(c);return [v.length,v.filter(s=>s.size>1).length]})()")
        print('senarai murid KPI:', kpis, '| by name only:', by_name)
        assert [int(kpis[0]), int(kpis[1])] == by_name, 'one entry per pupil name'
        assert int(kpis[0]) == pg.locator('#awList .ms').count() > 0, 'every pupil by default'
        pg.check('#msMulti')
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
    # the dashboard no longer shows gallery photos (Galeri tab only)
    pg.click('.nav[data-v=dashboard]')
    expect(pg.locator('#v-dashboard img')).to_have_count(0)
    pg.click('.nav[data-v=galeri]')
    pg.locator('#gal .del').first.click()
    expect(pg.locator('#gal .ph')).to_have_count(0)
    # camera: Escape cancels without uploading; otherwise the caption is asked for, then uploaded
    pg.set_input_files('#camFile', files=[IMG])
    expect(pg.locator('#cam')).to_have_class('lb on')
    pg.keyboard.press('Escape')
    expect(pg.locator('#cam')).not_to_have_class('lb on')
    pg.set_input_files('#camFile', files=[IMG])
    expect(pg.locator('#camCap')).to_be_focused()
    pg.select_option('#camKat', 'Persiapan')
    pg.fill('#camCap', 'Raptai di dewan')
    shot(pg, 'demo-galeri-kamera')
    pg.keyboard.press('Enter')
    expect(pg.locator('#gal figcaption')).to_contain_text('Raptai di dewan', timeout=8000)
    assert pg.evaluate("D.galeri.length===1 && D.galeri[0].kat==='Persiapan'")
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
    # kehadiran: pick a class → each pupil once with all their awards → tick present
    # h4 is a HEM award (27 Nov): ticking the pupil present on 28 Nov must leave it unmarked
    pg.evaluate("call('addPenerima',{rows:[{id:'h1',aid:D.anugerah[0].id,kelas:'4 KREATIF',nama:'MURID HADIR'},{id:'h2',aid:D.anugerah[1].id,kelas:'4 KREATIF',nama:'MURID HADIR'},{id:'h3',aid:D.anugerah[0].id,kelas:'4 KREATIF',nama:'MURID LAIN'},{id:'h4',aid:D.anugerah.find(a=>a.kat==='H').id,kelas:'4 KREATIF',nama:'MURID HADIR'}]},{quiet:true})")
    pg.click('.nav[data-v=kehadiran]')
    pg.select_option('#hdHari', '3')
    expect(pg.locator('#hd .empty')).to_contain_text('Pilih kelas')
    pg.select_option('#hdKls', '4 KREATIF')
    row = pg.locator('#hd .ms.hd', has_text='MURID HADIR')
    expect(row.locator('.b')).to_have_count(2)
    row.click()
    expect(row.locator('.ms-n small')).to_contain_text('✓ HADIR')
    assert pg.evaluate("D.penerima.filter(p=>p.nama==='MURID HADIR'&&p.id!=='h4').every(p=>p.hadir)"), 'every award row of the pupil on that day marked'
    assert not pg.evaluate("D.penerima.find(p=>p.id==='h4').hadir"), 'the 27 Nov award is not marked from 28 Nov'
    assert not pg.evaluate("D.penerima.find(p=>p.nama==='MURID LAIN').hadir")
    pg.evaluate('refresh(true)'); pg.wait_for_timeout(300)
    expect(pg.locator('#hd .ms.hd', has_text='MURID HADIR').locator('input')).to_be_checked()
    shot(pg, 'demo-kehadiran')
    # kehadiran semua: every recipient from Tahun 1-6 in one list, class shown on each row
    pg.select_option('#hdKls', 'SEMUA')
    expect(pg.locator('#hd .ms.hd')).to_have_count(pg.evaluate("studentMap('ALL').filter(s=>s.items.some(({a,p})=>hariOf(a,p)==='3')).length"))
    expect(pg.locator('#hd .ms.hd', has_text='MURID HADIR').locator('.ms-n small')).to_contain_text('4 KREATIF · ✓ HADIR')
    pg.select_option('#hdKls', '4 KREATIF')
    pg.locator('#hd .ms.hd', has_text='MURID HADIR').click()
    expect(pg.locator('#hd .ms.hd', has_text='MURID HADIR').locator('.ms-n small')).to_have_text('BELUM HADIR')
    # 21 Nov: every Year 6 pupil on the school list, award or not; a pupil without an award is ticked in t6
    pg.select_option('#hdHari', '1')
    pg.select_option('#hdKls', '6 KRITIS')
    expect(pg.locator('#hd .ms.hd')).to_have_count(4)
    t6row = pg.locator('#hd .ms.hd').first
    expect(t6row.locator('.b')).to_have_text('Majlis T6')
    t6row.click()
    expect(pg.locator('#hd .ms.hd').first.locator('.ms-n small')).to_contain_text('✓ HADIR')
    assert pg.evaluate("D.t6.some(t=>t.kelas==='6 KRITIS'&&t.hadir)"), 'Year 6 attendance saved'
    # Kehadiran report: preview first, summary by class with penerima / bukan penerima, then the pupils
    pg.click('#hdDl')
    expect(pg.locator('#pvS')).to_contain_text('Word · 4 murid · 1 hadir · 1 kelas')
    pv = pg.frame_locator('#pvF')
    expect(pv.locator('h2', has_text='Ringkasan ikut kelas')).to_be_visible()
    expect(pv.locator('tr.tot td')).to_have_text(['JUMLAH', '4', '1', '3', '25%', '0 / 0', '1 / 4'])
    expect(pv.get_by_role('cell', name='Bukan penerima', exact=True)).to_have_count(4)
    expect(pv.get_by_role('cell', name='TIDAK HADIR', exact=True)).to_have_count(3)
    with pg.expect_download() as dl:
        pg.click('#pvOk')
    assert dl.value.suggested_filename == 'Kehadiran-2026-11-21-6-KRITIS.doc'
    pg.select_option('#hdFmt', 'xlsx')
    pg.click('#hdDl')
    expect(pg.locator('#pvS')).to_contain_text('Excel')
    with pg.expect_download() as dl:
        pg.click('#pvOk')
    import openpyxl
    wb = openpyxl.load_workbook(open(dl.value.path(), 'rb'))
    assert wb.sheetnames == ['Ringkasan', 'Senarai'], wb.sheetnames
    assert list(wb['Ringkasan'].values)[-1] == ('JUMLAH', 4, 1, 3, '25%', '0 / 0', '1 / 4')
    assert len(list(wb['Senarai'].values)) == 5
    pg.select_option('#hdFmt', 'doc')
    pg.select_option('#hdHari', '3')
    pg.select_option('#hdKls', 'SEMUA')  # other days: every pupil is a penerima, no bukan penerima columns
    pg.click('#hdDl')
    expect(pg.frame_locator('#pvF').locator('th', has_text='Bukan penerima')).to_have_count(0)
    pg.click('#pvC')
    # dashboard: Penerima counts pupils once (MURID HADIR has 3 awards); Tahun → kelas → murid drill-down
    pg.click('.nav[data-v=dashboard]')
    assert pg.evaluate("D.penerima.filter(p=>p.nama==='MURID HADIR').length") == 3
    uniq = pg.evaluate("new Set(D.penerima.map(p=>p.nama)).size")
    expect(pg.locator('#v-dashboard .kpi')).to_have_count(2)
    expect(pg.locator('#v-dashboard .kpi .n').nth(1)).to_have_text(str(uniq))
    for gone in ['Jawatankuasa pelaksana', 'Acara dalam tentatif', 'GALERI FOTO']:
        expect(pg.locator('#v-dashboard')).not_to_contain_text(gone)
    expect(pg.locator('#v-dashboard')).to_contain_text('STATUS PERSIAPAN JAWATANKUASA')
    expect(pg.locator('#v-dashboard')).to_contain_text('Kategori anugerah')
    cols = pg.eval_on_selector_all('#dxT .dx-col b', 'e=>e.map(x=>+x.textContent)')
    assert len(cols) == 6 and sum(cols) == uniq, cols
    pg.locator('#dxT .dx-col').nth(3).click()  # Tahun 4
    expect(pg.locator('#dxT .dx-row')).to_have_count(5)  # every class of Tahun 4, empty ones show 0
    pg.locator('#dxT .dx-row', has_text='4 KREATIF').click()
    expect(pg.locator('#dxT .dx-pl > div', has_text='MURID HADIR').locator('small').first).to_have_text('3 anugerah')
    pg.evaluate('refresh(true)'); pg.wait_for_timeout(300)
    expect(pg.locator('#dxT .dx-path')).to_contain_text('4 KREATIF')  # the drill-down survives the live refresh
    pg.locator('#dxT .dx-path button').first.click()
    expect(pg.locator('#dxT .dx-col')).to_have_count(6)
    # kategori: HEM → Tahun 4 → 4 KREATIF shows MURID HADIR with only the HEM award
    pg.locator('#dxK .dx-leg .chip', has_text='Hal Ehwal Murid').click()
    pg.locator('#dxK .dx-row', has_text='Tahun 4').click()
    pg.locator('#dxK .dx-row', has_text='4 KREATIF').click()
    expect(pg.locator('#dxK .dx-pl > div', has_text='MURID HADIR').locator('small').first).to_have_text('1 anugerah')
    pg.locator('#dxK .dx-seg button', has_text='Ikut Kelas').click()
    expect(pg.locator('#dxK .dx-row')).to_have_count(pg.evaluate('dxKelas(dxMurid()).length'))
    pg.locator('#dxK .dx-leg .chip', has_text='Semua').click()
    shot(pg, 'demo-dashboard')
    # Gambar Murid: one photo per pupil, filled by class, then seen in Senarai Murid, Kehadiran and the dashboard
    pg.click('.nav[data-v=gambar]')
    expect(pg.locator('#gm .empty')).to_contain_text('Pilih kelas')
    pg.select_option('#gmK', '4 KREATIF')
    card = pg.locator('#gm .gm-card', has_text='MURID HADIR')
    expect(card.locator('.gm-st')).to_have_text('BELUM ADA FOTO')
    card.locator('[data-mfoto]').click()  # choose: camera with a frame, or the gallery
    expect(pg.locator('#fc')).to_have_class('lb on')
    expect(pg.locator('#fcT')).to_have_text('MURID HADIR')
    pg.set_input_files('#fcFile', files=[IMG])
    expect(pg.locator('#fc')).not_to_have_class('lb on')
    expect(pg.locator('#gm .gm-card', has_text='MURID HADIR').locator('.gm-st')).to_have_text('✓ ADA FOTO', timeout=8000)
    # in-app camera (fake device): the view is the poster's 3:4 box with face and shoulder guides; the shot replaces the photo
    old = pg.evaluate("fotoOf({nama:'MURID HADIR',kelas:'4 KREATIF'})")
    pg.locator('#gm .gm-card', has_text='MURID HADIR').locator('[data-mfoto]').click()
    pg.click('#fcCam')
    expect(pg.locator('#fcSnap')).to_be_enabled(timeout=8000)
    box = pg.locator('#fcView').bounding_box()
    assert abs(box['width'] / box['height'] - 0.75) < 0.01, box
    expect(pg.locator('#fcView .fc-oval')).to_be_visible()
    expect(pg.locator('#fcView .fc-sh')).to_be_visible()
    pg.click('#fcSnap')
    expect(pg.locator('#fcUse')).to_be_visible()
    expect(pg.locator('#fcView .fc-oval')).to_be_hidden()  # guides off to check the shot
    pg.click('#fcAgain')
    expect(pg.locator('#fcSnap')).to_be_visible()
    pg.click('#fcSnap')
    assert pg.evaluate("[$('#fcShot').width,$('#fcShot').height]") == [900, 1200]
    pg.click('#fcUse')
    pg.wait_for_function(f"fotoOf({{nama:'MURID HADIR',kelas:'4 KREATIF'}})!=={old!r}", timeout=8000)
    assert pg.evaluate('FC.stream===null'), 'camera turned off after use'
    # delete, no PIN: Padam foto on the card, and Padam foto semasa in the photo window (both confirm first)
    hadir = lambda: pg.locator('#gm .gm-card', has_text='MURID HADIR')
    hadir().locator('.gm-del').click()
    expect(hadir().locator('.gm-st')).to_have_text('BELUM ADA FOTO', timeout=8000)
    expect(hadir().locator('.gm-del')).to_have_count(0)
    hadir().locator('[data-mfoto]').click()
    expect(pg.locator('#fcDel')).to_be_hidden()  # no photo yet, nothing to delete
    pg.set_input_files('#fcFile', files=[IMG])
    expect(hadir().locator('.gm-st')).to_have_text('✓ ADA FOTO', timeout=8000)
    hadir().locator('[data-mfoto]').click()
    pg.click('#fcDel')
    expect(pg.locator('#fc')).not_to_have_class('lb on')
    expect(hadir().locator('.gm-st')).to_have_text('BELUM ADA FOTO', timeout=8000)
    hadir().locator('[data-mfoto]').click()
    pg.set_input_files('#fcFile', files=[IMG])
    expect(hadir().locator('.gm-st')).to_have_text('✓ ADA FOTO', timeout=8000)
    assert pg.evaluate("localCall({action:'delT6Foto',nama:'MURID HADIR',kelas:'4 KREATIF'}).ok"), 'delete needs no PIN'
    pg.evaluate("refresh()")
    expect(hadir().locator('.gm-st')).to_have_text('BELUM ADA FOTO', timeout=8000)
    hadir().locator('[data-mfoto]').click()
    pg.set_input_files('#fcFile', files=[IMG])
    expect(hadir().locator('.gm-st')).to_have_text('✓ ADA FOTO', timeout=8000)
    # upload many: "murid lain.png" matches MURID LAIN, an unknown name is left out; nothing saved before Simpan
    pg.set_input_files('#gmFiles', files=[{**IMG, 'name': 'murid lain.png'}, {**IMG, 'name': 'tiada nama ini.png'}])
    expect(pg.locator('#gm .gm-br')).to_have_count(2)
    assert pg.locator('#gm select[data-gb="0"]').input_value() == 'MURID LAIN|4 KREATIF'
    assert pg.locator('#gm select[data-gb="1"]').input_value() == ''
    expect(pg.locator('#gmBOk')).to_have_text('Simpan 1 foto')
    assert not pg.evaluate("fotoOf({nama:'MURID LAIN',kelas:'4 KREATIF'})"), 'nothing saved before Simpan'
    pg.select_option('#gm select[data-gb="1"]', 'MURID LAIN|4 KREATIF')  # same pupil twice: blocked
    expect(pg.locator('#gm .warnmsg')).to_contain_text('MURID LAIN')
    expect(pg.locator('#gmBOk')).to_be_disabled()
    pg.select_option('#gm select[data-gb="1"]', '')
    pg.click('#gmBOk')
    pg.wait_for_function("fotoOf({nama:'MURID LAIN',kelas:'4 KREATIF'})", timeout=8000)
    expect(pg.locator('#gm .gm-br')).to_have_count(0)
    pg.check('#gmX')  # only pupils without a photo: none left in 4 KREATIF
    expect(pg.locator('#gm .empty')).to_contain_text('sudah ada foto')
    pg.uncheck('#gmX')
    # the same photo shows elsewhere, view only
    pg.click('.nav[data-v=anugerah]')
    pg.click('#awMode [data-m=murid]')
    expect(pg.locator('#awList .ms', has_text='MURID HADIR').locator('.foto-mini img')).to_have_count(1)
    pg.click('#awMode [data-m=kad]')
    pg.click('.nav[data-v=kehadiran]')
    pg.select_option('#hdHari', '3')
    pg.select_option('#hdKls', '4 KREATIF')
    expect(pg.locator('#hd .ms.hd', has_text='MURID HADIR').locator('.foto-mini img')).to_have_count(1)
    pg.click('.nav[data-v=dashboard]')
    pg.locator('#dxT .dx-col').nth(3).click()
    pg.locator('#dxT .dx-row', has_text='4 KREATIF').click()
    expect(pg.locator('#dxT .dx-pl > div', has_text='MURID LAIN').locator('.foto-mini img')).to_have_count(1)
    pg.locator('#dxT .dx-path button').first.click()
    # hari penyampaian: subject awards Tahun 6 on 21 Nov, Tahun 1-5 on 28 Nov, HEM on 27 Nov; ONE letter per pupil lists each award with its date
    pg.evaluate("(()=>{const m=D.anugerah.find(a=>a.nama==='Anugerah Matematik').id,h=D.anugerah.find(a=>a.kat==='H').id;return call('addPenerima',{rows:[{id:'d1',aid:m,kelas:'6 KREATIF',nama:'MURID ENAM'},{id:'d2',aid:h,kelas:'6 KREATIF',nama:'MURID ENAM'},{id:'d3',aid:m,kelas:'5 KREATIF',nama:'MURID LIMA'},{id:'d4',aid:h,kelas:'3 KREATIF',nama:'MURID HEM'}]},{quiet:true})})()")
    letter = lambda n: [x for x in pg.evaluate('suratHTML().html').split('class="pb"') if f'<b>{n}</b>' in x]
    modes = pg.evaluate("Object.fromEntries(D.anugerah.map(a=>[a.nama,hariMode(a)]))")
    assert modes['Anugerah Sains'] == 'T' and modes['Anugerah NILAM'] == '3' and modes['Anugerah Pengawas'] == '2', modes  # 'SAINS' contains 'AINS'
    six, five = letter('MURID ENAM'), letter('MURID LIMA')
    assert len(six) == 1 and '21 November 2026 (Sabtu)' in six[0] and '27 November 2026 (Jumaat)' in six[0] and '28 November' not in six[0], six
    assert six[0].index('Anugerah Matematik') < six[0].index('21 November') < six[0].index('27 November'), 'awards in date order'
    assert len(five) == 1 and '28 November 2026 (Sabtu)' in five[0] and '21 November' not in five[0]
    # parents are invited on hari 1 and 3 only; hari 2 (HEM) is for pupils
    hem = letter('MURID HEM')
    assert 'menjemput tuan/puan hadir bersama anak pada <b>21 November 2026 (Sabtu)</b>' in six[0] and 'tidak diperlukan pada <b>27 November 2026 (Jumaat)</b>' in six[0], six[0]
    assert 'menjemput tuan/puan hadir bersama anak pada <b>28 November 2026 (Sabtu)</b>' in five[0] and 'tidak diperlukan' not in five[0]
    assert len(hem) == 1 and 'menjemput' not in hem[0] and 'melibatkan murid sahaja' in hem[0] and 'kehadiran ibu bapa/penjaga tidak diperlukan' in hem[0]
    assert 'MAJLIS ANUGERAH SRI BITARA SK BANDAR TAWAU' in six[0] and 'sempena Majlis Anugerah Sri Bitara' in six[0] and 'Majlis Anugerah Apresiasi' not in six[0] and 'MAJLIS APRESIASI' not in six[0]
    # Tetapan › Hari Penyampaian: times per day and a per-anugerah override
    pg.click('.nav[data-v=tetapan]')
    pg.click('#admin .chip[data-t=hari]')
    pg.fill('#admin [data-h="1"] [data-k=mula]', '08:00')
    pg.fill('#admin [data-h="1"] [data-k=tamat]', '11:30')
    mat = pg.evaluate("D.anugerah.find(a=>a.nama==='Anugerah Matematik').id")
    expect(pg.locator(f'#admin [data-hari="{mat}"]')).to_have_value('T')
    pg.click('#hSave')
    pg.wait_for_function("D.settings.hari['1'].tamat==='11:30'")
    assert '8.00 pagi hingga 11.30 pagi' in letter('MURID ENAM')[0]
    pg.select_option(f'#admin [data-hari="{mat}"]', '2')
    pg.click('#hSave')
    pg.wait_for_function(f"D.settings.hariAw['{mat}']==='2'")
    assert '21 November' not in letter('MURID ENAM')[0], 'override: Matematik now on 27 Nov for everyone'
    pg.select_option(f'#admin [data-hari="{mat}"]', 'T')
    pg.click('#hSave')
    pg.wait_for_function(f"D.settings.hariAw['{mat}']==='T'")
    pg.evaluate("call('delPenerima',{ids:['d1','d2','d3','d4']},{quiet:true})")
    # Ketua Kelas & Pen. Ketua Kelas: ticked pupils get a role (saved as catatan)
    pg.click('.nav[data-v=anugerah]')
    pg.locator('#awGrid .aw', has_text='Ketua Kelas').click()
    # a class with no Ketua Kelas yet (the real xlsx already fills some classes)
    kk_aid = pg.evaluate("D.anugerah.find(a=>/ketua kelas/i.test(a.nama)).id")
    expect(pg.locator('#adKls')).to_be_visible(timeout=8000)
    kk_kls = pg.evaluate(f"[...$('#adKls').options].map(o=>o.value).find(k=>k&&ROSTER.filter(r=>r.kelas===k).length>=2&&!D.penerima.some(p=>p.aid==='{kk_aid}'&&p.kelas===k))")
    if not kk_kls:  # every class already filled: empty one (demo data only)
        kk_kls = pg.evaluate("[...$('#adKls').options].map(o=>o.value).find(k=>k&&ROSTER.filter(r=>r.kelas===k).length>=2)")
        pg.evaluate(f"call('delPenerima',{{ids:D.penerima.filter(p=>p.aid==='{kk_aid}'&&p.kelas==='{kk_kls}').map(p=>p.id)}},{{quiet:true}})")
        pg.wait_for_function(f"!D.penerima.some(p=>p.aid==='{kk_aid}'&&p.kelas==='{kk_kls}')", timeout=8000)
    kk_n = pg.evaluate(f"D.penerima.filter(p=>p.aid==='{kk_aid}').length")
    pg.select_option('#adKls', kk_kls)
    pg.fill('#adMan', 'murid manual')
    sts = pg.locator('#addp .studs .st')
    sts.nth(0).click(); sts.nth(1).click()
    expect(pg.locator('#addp [data-kk]')).to_have_count(4)
    assert pg.input_value('#adMan') == 'murid manual', 'typed name kept when the box redraws'
    first, second = sts.nth(0).inner_text().strip(), sts.nth(1).inner_text().strip()
    expect(pg.locator(f'#addp [data-kk="{first}"].on')).to_have_text('Ketua Kelas')
    expect(pg.locator(f'#addp [data-kk="{second}"].on')).to_have_text('Pen. Ketua Kelas')
    pg.locator(f'#addp [data-kk="{second}"][data-r="0"]').click()
    expect(pg.locator('#addp .warnmsg')).to_contain_text('Lebih daripada seorang Ketua Kelas')
    pg.locator(f'#addp [data-kk="{first}"][data-r="1"]').click()
    expect(pg.locator('#addp .warnmsg')).to_have_count(0)
    shot(pg, 'demo-ketua-kelas')
    pg.click('#adGo')
    pg.wait_for_function(f"D.penerima.filter(p=>p.aid==='{kk_aid}').length==={kk_n + 3}")
    role = pg.evaluate(f"Object.fromEntries(D.penerima.filter(p=>p.aid==='{kk_aid}'&&p.kelas==='{kk_kls}').map(p=>[p.nama,p.catatan]))")
    assert role == {first: 'PEN. KETUA KELAS', second: 'KETUA KELAS', 'MURID MANUAL': ''}, role
    expect(pg.locator('#addp .st.have', has_text=second)).to_contain_text('SUDAH · KETUA KELAS')
    pg.keyboard.press('Escape')
    pg.click('.nav[data-v=tetapan]')
    # settings: date + public names off by default → lock hides names
    pg.click('#admin .chip[data-t=majlis]')
    pg.fill('#sTarikh', '2026-12-01')
    pg.click('#sSave')
    pg.wait_for_function('D.settings.tarikh==="2026-12-01"')
    # Kunci Anugerah: lock all, unlock all, or pick from the list
    pg.click('#admin .chip[data-t=kunci]')
    pg.click('#admin [data-ka="1"]')
    pg.wait_for_function('D.settings.dikunci.length===D.anugerah.length')
    expect(pg.locator('#admin .setp.on [data-kunci]:checked')).to_have_count(pg.evaluate('D.anugerah.length'))
    pg.click('#admin [data-ka=""]')
    pg.wait_for_function('D.settings.dikunci.length===0')
    pg.locator('#admin .setp.on .set-row').nth(1).click()
    pg.wait_for_function('D.settings.dikunci.length===1')
    shot(pg, 'tetapan-kunci')
    pg.locator('#admin .setp.on .set-row').nth(1).click()
    pg.wait_for_function('D.settings.dikunci.length===0')
    # Persembahan: admin adds performances, pupils are picked like anugerah, letters and certificates are generated
    naw, nstud = pg.evaluate('D.anugerah.length'), pg.evaluate("studentMap('ALL').length")
    pg.click('.nav[data-v=persembahan]')
    expect(pg.locator('#psGrid')).to_contain_text('Belum ada persembahan')
    for i, n in enumerate(['Tarian Sabah', 'Nasyid']):
        pg.click('#rePs [data-a=add]')
        pg.locator('#rePs .fi[data-k=nama]').nth(i).fill(n)
    pg.click('#rePs [data-a=save]')
    expect(pg.locator('#psGrid .aw')).to_have_count(2, timeout=8000)
    assert pg.evaluate('D.anugerah.length') == naw, 'persembahan stay out of the anugerah list'
    pg.locator('#psGrid .aw', has_text='Tarian Sabah').click()
    expect(pg.locator('#drawer header')).to_contain_text('PERSEMBAHAN')
    pg.select_option('#adKls', '5 KREATIF')
    pg.fill('#adCat', 'Penari')
    pg.locator('#addp .st input').nth(0).check(); pg.locator('#addp .st input').nth(1).check()
    pg.click('#adGo')
    expect(pg.locator('#drawer .rcp')).to_have_count(2, timeout=8000)
    expect(pg.locator('#drawer .tg')).to_have_count(0)
    pg.keyboard.press('Escape')
    expect(pg.locator('#psGrid .aw', has_text='Tarian Sabah')).to_contain_text('2 murid')
    assert pg.evaluate("studentMap('ALL').length") == nstud, 'performers are not counted as award recipients'
    # whole-table anugerah saves keep the persembahan
    pg.evaluate("call('saveTable',{table:'anugerah',rows:D.anugerah},{quiet:true})")
    assert pg.evaluate('D.persembahan.length') == 2 and pg.evaluate('D.peserta.length') == 2
    pg.click('#psSurat')
    expect(pg.frame_locator('#pvF').locator('body')).to_contain_text('MAKLUMAN PENGLIBATAN MURID DALAM PERSEMBAHAN')
    expect(pg.frame_locator('#pvF').locator('body')).to_contain_text('Tarian Sabah (PENARI)')
    expect(pg.frame_locator('#pvF').locator('img[src$="tandatangan-guru-besar.png"]')).to_have_count(2)  # one letter per pupil, each signed
    pg.click('#pvC')
    pg.click('#psSijil')
    expect(pg.frame_locator('#pvF').locator('.sj')).to_have_count(2)
    expect(pg.frame_locator('#pvF').locator('.sj').first).to_contain_text('sebagai PENARI')
    expect(pg.frame_locator('#pvF').locator('.sj img.ttd')).to_have_count(2)  # Guru Besar's signature on every sijil
    expect(pg.locator('#pvOk')).to_contain_text('Cetak / PDF')
    shot(pg, 'sijil-preview')
    pg.click('#pvC')
    pg.click('#psSijilW')  # Word version: same two certificates, landscape .doc
    expect(pg.locator('#pvOk')).to_contain_text('Muat turun')
    expect(pg.frame_locator('#pvF').locator('body')).to_contain_text('sebagai PENARI')
    with pg.expect_download() as dl:
        pg.click('#pvOk')
    assert dl.value.suggested_filename == 'Sijil-Penghargaan-Persembahan.doc'
    doc = pathlib.Path(dl.value.path()).read_text(encoding='utf-8-sig')
    assert 'mso-page-orientation:landscape' in doc and doc.count('SIJIL PENGHARGAAN') == 2
    assert doc.count('tandatangan-guru-besar.png') == 2
    pg.click('#psXls')  # Excel list: one row per pupil per persembahan
    expect(pg.frame_locator('#pvF').locator('tr')).to_have_count(3)
    with pg.expect_download() as dl:
        pg.click('#pvOk')
    assert dl.value.suggested_filename == 'Senarai-Murid-Persembahan.xlsx'
    import openpyxl
    ws = openpyxl.load_workbook(open(dl.value.path(), 'rb')).active  # file object: the temp path has no .xlsx extension
    rows = list(ws.values)
    assert rows[0] == ('Bil', 'Persembahan', 'Nama', 'Kelas', 'Tahun', 'Peranan', 'Tarikh') and len(rows) == 3, rows
    assert rows[1][6] == '28 November 2026 (Sabtu)', rows[1]
    assert rows[1][1] == 'Tarian Sabah' and rows[1][3] == '5 KREATIF' and rows[1][5] == 'PENARI', rows[1]
    pg.click('.nav[data-v=tetapan]')
    pg.click('#admin .chip[data-t=sistem]')
    pg.locator('#admin .setp.on button', has_text='Kunci').click()
    pg.wait_for_timeout(500)
    assert not pg.evaluate('document.body.classList.contains("admin")')
    expect(pg.locator('.nav[data-v=kehadiran]')).to_be_visible()  # Kehadiran is open to everyone
    # visitor with only the link: pupil list is there and adding works without the PIN
    pg.click('.nav[data-v=anugerah]')
    pg.locator('#awGrid .aw').nth(2).click()
    pg.select_option('#adKls', '4 KREATIF')
    pg.locator('#addp .st input').first.check()
    pg.click('#adGo')
    expect(pg.locator('#toast')).to_contain_text('penerima ditambah', timeout=8000)
    assert pg.evaluate("localCall({action:'delPenerima',ids:['x']}).ok"), 'visitor may remove a pupil'
    assert pg.evaluate("(()=>{try{localCall({action:'saveTable',table:'ajk',rows:[]})}catch(e){return e.message}})()") == 'PIN salah'
    # lock this anugerah: locking and unlocking both need the admin PIN; entry stops while locked
    aid = pg.evaluate('DRAWER')
    assert pg.evaluate(f"(()=>{{try{{localCall({{action:'setKunci',ids:['{aid}'],kunci:true}})}}catch(e){{return e.message}}}})()") == 'PIN salah'
    pg.click('#drawer .lockbar summary')
    pg.fill('#awKunciPin', '000000'); pg.click('#awKunciF button')
    expect(pg.locator('#toast')).to_contain_text('PIN salah')
    assert not pg.evaluate('D.settings.dikunci.length')
    pg.fill('#awKunciPin', '123456'); pg.click('#awKunciF button')
    expect(pg.locator('#drawer .lockbar')).to_contain_text('dikunci')
    expect(pg.locator('#addp')).to_have_count(0)
    expect(pg.locator('#drawer .del-p')).to_have_count(0)
    assert pg.evaluate(f"(()=>{{try{{localCall({{action:'addPenerima',rows:[{{id:'z',aid:'{aid}',nama:'X',kelas:'4 KREATIF'}}]}})}}catch(e){{return e.message}}}})()").startswith('Anugerah ini dikunci')
    other = pg.evaluate(f"D.anugerah.find(a=>a.id!=='{aid}').id")
    assert pg.evaluate(f"localCall({{action:'addPenerima',rows:[{{id:'z2',aid:'{other}',nama:'X',kelas:'4 KREATIF'}}]}}).added") == 1, 'other anugerah stay open'
    assert pg.evaluate(f"(()=>{{try{{localCall({{action:'setKunci',ids:['{aid}'],kunci:false}})}}catch(e){{return e.message}}}})()") == 'PIN salah'
    pg.fill('#awKunciPin', '123456'); pg.click('#awKunciF button')
    expect(pg.locator('#addp')).to_be_visible()
    assert not pg.evaluate('PIN'), 'unlocking does not log the visitor in'
    pg.keyboard.press('Escape')
    # Kokurikulum: same pupil again for another achievement; the exact same achievement is skipped; other kategori stay one row per pupil
    ko = pg.evaluate("D.anugerah.find(a=>a.kat==='KO').id")
    row = lambda i, aid, cat: f"{{id:'{i}',aid:'{aid}',kelas:'5 KREATIF',tahun:'5',nama:'MURID KOKO',catatan:'{cat}'}}"
    assert pg.evaluate(f"call('addPenerima',{{rows:[{row('k1', ko, 'BOLA SEPAK – JOHAN – DAERAH')},{row('k2', ko, 'OLAHRAGA – NAIB JOHAN – NEGERI')},{row('k3', ko, 'BOLA SEPAK – JOHAN – DAERAH')}]}},{{quiet:true}}).then(j=>j.added)") == 2
    assert pg.evaluate(f"call('addPenerima',{{rows:[{row('k4', other, 'A')},{row('k5', other, 'B')}]}},{{quiet:true}}).then(j=>j.added)") == 1, 'non-Kokurikulum keeps one row per pupil'
    pg.evaluate("call('setCatatan',{ids:['k2'],catatan:' olahraga – johan – negeri '},{quiet:true})")
    s = pg.evaluate(f"(()=>{{const s=studentMap('ALL').find(s=>s.nama==='MURID KOKO');const i=s.items.find(i=>i.a.id==='{ko}');return [i.p.catatan,i.ps.length,counts(i.a).n]}})()")
    assert s == ['BOLA SEPAK – JOHAN – DAERAH; OLAHRAGA – JOHAN – NEGERI', 2, pg.evaluate(f"new Set(D.penerima.filter(p=>p.aid==='{ko}').map(p=>p.nama+'|'+p.kelas)).size")], s
    assert pg.evaluate("posterCanvas(studentMap('ALL').find(s=>s.nama==='MURID KOKO'),'KO').then(c=>[c.width,c.height])") == [1920, 1080]
    # the 'Semua poster' ZIP writer: read back by Python's zipfile (CRC, sizes, UTF-8 folder names)
    import io, zipfile
    zb = pg.evaluate("zipBlob([{name:'Kokurikulum/5 KREATIF - MURID KOKO.jpg',data:new Uint8Array([1,2,3,255])},{name:'Hal Ehwal Murid/Ä.jpg',data:new TextEncoder().encode('x'.repeat(5000))}]).arrayBuffer().then(b=>[...new Uint8Array(b)])")
    z = zipfile.ZipFile(io.BytesIO(bytes(zb)))
    assert z.testzip() is None and z.namelist() == ['Kokurikulum/5 KREATIF - MURID KOKO.jpg', 'Hal Ehwal Murid/Ä.jpg']
    assert z.read('Kokurikulum/5 KREATIF - MURID KOKO.jpg') == bytes([1, 2, 3, 255]) and len(z.read('Hal Ehwal Murid/Ä.jpg')) == 5000
    # Majlis T6: saved in capitals, only the fields sent change, photo can be removed; poster still draws with a broken photo
    t6 = "D.t6.find(t=>t.nama==='MURID CONTOH 6INO 1')"
    pg.evaluate("call('setT6',{nama:' murid contoh 6ino 1',kelas:'6 inovatif',hobi:'  bermain   catur '},{quiet:true})")
    pg.evaluate("call('setT6',{nama:'MURID CONTOH 6INO 1',kelas:'6 INOVATIF',cita:'doktor gigi'},{quiet:true})")
    pg.evaluate("call('upload',{purpose:'t6',nama:'MURID CONTOH 6INO 1',kelas:'6 INOVATIF',mime:'image/jpeg',data:'AAAA'},{quiet:true})")
    assert pg.evaluate(f"[{t6}.hobi,{t6}.cita,!!{t6}.src,D.t6.length]") == ['BERMAIN CATUR', 'DOKTOR GIGI', True, 4]  # + the 6 KRITIS pupil ticked in Kehadiran, 2 photos from Gambar Murid
    assert pg.evaluate(f"t6Canvas({t6}).then(c=>[c.width,c.height])") == [1920, 1080]
    pg.evaluate("call('delT6Foto',{nama:'MURID CONTOH 6INO 1',kelas:'6 INOVATIF'},{quiet:true})")
    assert pg.evaluate(f"{t6}.src") == ''
    # 'Excel + foto': a real .xlsx with the photo anchored in column B of its row
    import openpyxl
    xb = pg.evaluate("(async()=>{const c=document.createElement('canvas');c.width=30;c.height=40;c.getContext('2d').fillRect(0,0,30,40);const b=await xlsxFoto('Majlis T6',['Bil','Foto','Nama'],[[1,'','A & <B>'],[2,'','C']],[c.toDataURL('image/png'),'']);return [...new Uint8Array(await b.arrayBuffer())]})()")
    ws = openpyxl.load_workbook(io.BytesIO(bytes(xb))).active
    assert [c.value for c in ws[2]][::2] == [1, 'A & <B>'] and [(i.anchor._from.row, i.anchor._from.col) for i in ws._images] == [(1, 1)]
    pg.evaluate(f"PIN='123456';openAw('{ko}')")  # names are hidden from visitors here, so edit as admin
    pg.click('#drawer [data-ed=k1]')
    pg.fill('#drawer .ed-c input', 'Bola sepak – johan – zon')
    pg.click('#drawer .ed-c button')
    expect(pg.locator('#toast')).to_contain_text('Catatan disimpan')
    assert pg.evaluate("D.penerima.find(p=>p.id==='k1').catatan") == 'BOLA SEPAK – JOHAN – ZON'
    # one row per pupil in the panel, each achievement listed; Diterima marks all of the pupil's rows
    koko = pg.locator('#drawer .rcp', has_text='MURID KOKO')
    expect(koko).to_have_count(1)
    expect(koko.locator('.ach')).to_have_count(2)
    expect(pg.locator('#drawer header')).to_contain_text('pencapaian')
    koko.locator('.tg').click()
    assert pg.evaluate("D.penerima.filter(p=>['k1','k2'].includes(p.id)).map(p=>p.status)") == ['Diterima', 'Diterima']
    # Trofi Kokum: the same pupil in a second trophy award is still 1 trophy, with all 3 achievements
    sukan = pg.evaluate("D.anugerah.find(a=>/sukan dan permainan/i.test(a.nama)).id")
    pg.evaluate(f"call('addPenerima',{{rows:[{row('k6', sukan, 'BOLA JARING – JOHAN – ZON')}]}},{{quiet:true}})")
    assert pg.evaluate("(()=>{const s=trofiList().all.find(s=>s.nama==='MURID KOKO');return [s.items.length,s.n,trofiList().all.filter(s=>s.nama==='MURID KOKO').length]})()") == [2, 3, 1]
    # Ikon awards: own poster, never on the Kokurikulum achievement poster, never a Trofi Kokum trophy
    ikon = pg.evaluate("D.anugerah.find(a=>/^ikon kokurikulum/i.test(a.nama)).id")
    pg.evaluate(f"call('addPenerima',{{rows:[{row('k7', ikon, 'PENGAKAP')}]}},{{quiet:true}})")
    koko_s = "studentMap('ALL').find(s=>s.nama==='MURID KOKO')"
    assert pg.evaluate(f"Object.keys(POSTER_STYLE).filter(k=>{koko_s}.items.some(i=>posterKat(i.a)===k))") == ['K', 'KO', 'IKO']
    assert pg.evaluate("posterKat({kat:'KO',nama:'Anugerah Ikon Harapan Kokurikulum'})") == 'IKH'
    assert pg.evaluate(f"posterCanvas({koko_s},'IKO').then(c=>[c.width,c.height])") == [1920, 1080]
    assert pg.evaluate("trofiList().all.find(s=>s.nama==='MURID KOKO').n") == 3
    pg.keyboard.press('Escape')
    pg.click('.nav[data-v=anugerah]')
    pg.click('#awMode [data-m=trofi]')
    koko_tr = pg.locator('#awList table.trofi tr', has_text='MURID KOKO')
    expect(koko_tr).to_have_count(1)
    # Pencapaian Kokurikulum sub columns: Sukan & Permainan first, the pupil's other award's achievements in their own cell
    cells = koko_tr.locator('td').all_inner_texts()
    heads = pg.locator('#awList table.trofi tr').nth(1).locator('th').all_inner_texts()
    assert heads[0].upper().startswith('SUKAN') and cells[3 + heads.index(next(h for h in heads if 'SUKAN' in h.upper()))] == 'BOLA JARING – JOHAN – ZON', (heads, cells)
    assert 'OLAHRAGA – JOHAN – NEGERI' in cells[3 + [h.upper() for h in heads].index('BADAN BERUNIFORM')], cells
    pg.click('#trWord')
    expect(pg.frame_locator('#pvF').locator('body')).to_contain_text('PENCAPAIAN KOKURIKULUM', ignore_case=True)
    pg.click('#pvC')
    expect(pg.locator('#awList .ms-kpi .n').first).to_have_text(str(pg.evaluate('trofiList().all.length')))
    shot(pg, 'trofi-kokum')
    pg.click('#awMode [data-m=kad]')
    pg.evaluate("PIN=''")
    pg.keyboard.press('Escape')
    pg.click('.nav[data-v=dashboard]')
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
    for v in ['anugerah', 'persembahan', 'ajk', 'tentatif', 'galeri', 'tetapan']:
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
        pg.locator('#drawer [data-del]').first.click()
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
        # downloads: per kategori, keseluruhan, surat (each shows a preview first; Muat turun saves)
        def download(open_):
            open_()
            expect(pg.locator('#pv')).to_have_class('lb on')
            with pg.expect_download() as dl:
                pg.click('#pvOk')
            expect(pg.locator('#pv')).not_to_have_class('lb on')
            return dl.value
        pg.click('.nav[data-v=anugerah]')
        pg.click('#awDl')
        expect(pg.frame_locator('#pvF').locator('body')).to_contain_text(aw5)
        shot(pg, 'remote-preview')
        pg.click('#pvC')
        expect(pg.locator('#pv')).not_to_have_class('lb on')
        assert download(lambda: pg.click('#awDl')).suggested_filename == 'Senarai-Penerima-Keseluruhan.doc'
        pg.click('#awCats .chip[data-c=K]')
        d = download(lambda: pg.click('#awDl'))
        assert d.suggested_filename == 'Senarai-Penerima-Kurikulum.doc'
        assert aw5 in open(d.path(), encoding='utf-8-sig').read()
        pg.click('#awCats .chip[data-c=ALL]')
        surat_btn = lambda: pg.locator('#v-anugerah button', has_text='Surat jemputan').click()
        surat_btn()
        expect(pg.frame_locator('#pvF').locator('body')).to_contain_text('MURID BAHARU')
        pg.keyboard.press('Escape')
        expect(pg.locator('#pv')).not_to_have_class('lb on')
        assert download(surat_btn).suggested_filename == 'Surat-Jemputan-Penerima-Anugerah.doc'
        # by class, then one pupil (pupil wins), then back to everyone
        kls = pg.evaluate("studentMap('ALL').find(s=>s.nama==='MURID BAHARU').kelas")
        pg.select_option('#dlKls', kls)
        d = download(lambda: pg.click('#awDl'))
        assert d.suggested_filename == f"Senarai-Penerima-Keseluruhan-{kls.replace(' ', '-')}.doc"
        body = open(d.path(), encoding='utf-8-sig').read()
        assert 'MURID BAHARU' in body and all(p['nama'] not in body for p in pg.evaluate(f"D.penerima.filter(p=>!D.penerima.some(q=>q.nama===p.nama&&q.kelas==={kls!r}))")), 'only that class'
        pg.select_option('#dlMurid', 'MURID BAHARU')
        assert pg.evaluate('suratHTML().n') == 1
        assert download(surat_btn).suggested_filename == 'Surat-Jemputan-Penerima-Anugerah-MURID-BAHARU.doc'
        pg.select_option('#dlKls', '')
        assert pg.evaluate("$('#dlMurid').value") == '' and pg.evaluate('suratHTML().n') == names
        # same downloads as Excel / CSV
        pg.select_option('#dlFmt', 'xlsx')
        d = download(lambda: pg.click('#awDl'))
        assert d.suggested_filename == 'Senarai-Penerima-Keseluruhan.xlsx'
        assert open(d.path(), 'rb').read(2) == b'PK', 'real xlsx'
        pg.select_option('#dlFmt', 'csv')
        surat_btn()
        expect(pg.locator('#pvS')).to_contain_text('CSV')
        expect(pg.frame_locator('#pvF').locator('table')).to_contain_text('MURID BAHARU')
        with pg.expect_download() as dl:
            pg.click('#pvOk')
        assert dl.value.suggested_filename == 'Surat-Jemputan-Senarai-Mail-Merge.csv'
        merge = open(dl.value.path(), encoding='utf-8-sig').read()
        row = [l for l in merge.splitlines() if '"MURID BAHARU"' in l]
        assert len(row) == 1 and aw5 in row[0] and aw12 in row[0] and '"2"' in row[0], 'one merge row, both awards'
        pg.select_option('#dlFmt', 'doc')
        pg.click('#awMode button[data-m=murid]')
        assert download(lambda: pg.click('#msCsv')).suggested_filename == 'Pemetaan-Penerima-Sri-Bitara-2026.csv'
        pg.click('#awMode button[data-m=kad]')
        pg.click('.nav[data-v=tetapan]')
        # Catatan Pengarah: saved, admin-only, and its lines lead the laporan sections
        pg.click('#admin .chip[data-t=catatan]')
        pg.fill('#cK', 'Kerjasama erat semua AJK\n- Murid berdisiplin')
        pg.fill('#cL', 'Raptai lewat dimulakan')
        pg.fill('#cC', '1. Mulakan raptai lebih awal')
        shot(pg, 'remote-catatan')
        pg.click('#cSave')
        pg.wait_for_function("D.settings.catatan.kelemahan==='Raptai lewat dimulakan'", timeout=8000)
        assert 'catatan' not in pg.evaluate("remote().then(j=>j.settings)")
        lap = pg.evaluate('laporanHTML()')
        assert '<li>Murid berdisiplin</li>' in lap and '<li>Mulakan raptai lebih awal</li>' in lap, 'one point per line, markers dropped'
        assert lap.index('Raptai lewat dimulakan') < lap.index('Cadangan untuk penambahbaikan'), 'kelemahan section'
        assert 'Tiada kelemahan ketara' not in lap
        # tetapan downloads also preview first
        pg.click('#admin .chip[data-t=import]')
        assert download(lambda: pg.click('#admin button[onclick="exportCSV()"]')).suggested_filename == 'Penerima-Sri-Bitara-2026.csv'
        pg.click('#admin .chip[data-t=laporan]')
        pg.click('#admin button[onclick="wordLaporan()"]')
        expect(pg.frame_locator('#pvF').locator('body')).to_contain_text(aw5)
        pg.click('#pvC')
        assert download(lambda: pg.click('#admin button[onclick="wordLaporan()"]')).suggested_filename == 'Laporan-Sri-Bitara-2026.doc'
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
        # AJK download the lists without the PIN, but only while names are public
        pg.click('.nav[data-v=anugerah]')
        if XLSX:
            expect(pg.locator('#awDl')).to_be_visible()
            assert download(lambda: pg.click('#awDl')).suggested_filename == 'Senarai-Penerima-Keseluruhan.doc'
            # class / pupil pickers work without the PIN too
            assert not pg.evaluate('PIN')
            kls = pg.evaluate("$('#dlKls').options[1].value")
            pg.select_option('#dlKls', kls)
            assert download(lambda: pg.click('#awDl')).suggested_filename == f"Senarai-Penerima-Keseluruhan-{kls.replace(' ', '-')}.doc"
            nama = pg.evaluate("$('#dlMurid').options[1].value")
            pg.select_option('#dlMurid', nama)
            assert pg.evaluate('suratHTML().n') == 1
            assert download(lambda: pg.locator('#v-anugerah button', has_text='Surat jemputan').click()).suggested_filename.startswith('Surat-Jemputan-Penerima-Anugerah-')
            pg.select_option('#dlKls', '')
        else:
            expect(pg.locator('#awDl')).to_be_hidden()
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
