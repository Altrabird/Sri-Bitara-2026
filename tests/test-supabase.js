// Ujian Edge Function Supabase (supabase/functions/api). MEMADAM DATA — jalankan hanya pada projek kosong / ujian.
// Usage: node tests/test-supabase.js <api-url> <pin>
const assert = require('assert');
const [API, PIN] = process.argv.slice(2);
if (!API || !PIN) { console.error('Usage: node tests/test-supabase.js <api-url> <pin>'); process.exit(1); }

const post = (b) => fetch(API, { method: 'POST', headers: { 'Content-Type': 'text/plain;charset=utf-8' }, body: JSON.stringify({ pin: PIN, ...b }) }).then((r) => r.json());
const call = async (b) => { const j = await post(b); assert(j.ok, b.action + ': ' + j.error); return j; };
const pub = () => fetch(API + '?action=public').then((r) => r.json());
// ?t= skips the CDN copy, which can outlive a deleted file
const status = (u) => fetch(u + '?t=' + Date.now()).then((r) => r.status);
const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==';

(async () => {
  assert.strictEqual((await post({ action: 'admin', pin: 'salah' })).error, 'PIN salah');

  await call({ action: 'saveTable', table: 'tentatif', rows: [{ id: 't2', acara: 'Hari 1' }, { id: 't1', masa: '07:00', acara: 'Ketibaan', pic: 'AJK' }] });
  await call({ action: 'replacePenerima', anugerah: [{ id: 'a1', kat: 'akademik', nama: 'Anugerah Dekan', sasaran: 3 }],
    penerima: [{ id: 'p1', aid: 'a1', tahun: '6', kelas: '6 BESTARI', nama: 'ALI', catatan: '', status: '' }] });
  let j = await call({ action: 'addPenerima', rows: [{ id: 'p2', aid: 'a1', kelas: '4 kreatif', nama: ' siti  aminah ' }, { id: 'p3', aid: 'a1', kelas: '6 BESTARI', nama: 'ali' }] });
  assert.strictEqual(j.added, 1, 'duplicate pupil skipped');
  const p2 = j.data.penerima.find((p) => p.id === 'p2');
  assert.deepStrictEqual([p2.nama, p2.kelas, p2.tahun], ['SITI AMINAH', '4 KREATIF', '4']);
  assert.deepStrictEqual(j.data.tentatif.map((t) => t.id), ['t2', 't1'], 'row order kept');
  assert.strictEqual(j.data.tentatif[0].masa, '', 'missing fields become empty strings');
  assert.strictEqual(j.data.anugerah[0].sasaran, '3');
  // visitors with only the link (no PIN) may add pupils and read the roster, nothing else
  const vis = (b) => fetch(API, { method: 'POST', body: JSON.stringify(b) }).then((r) => r.json());
  j = await vis({ action: 'addPenerima', rows: [{ id: 'p4', aid: 'a1', kelas: '5 KREATIF', nama: 'ABU' }] });
  assert(j.ok && j.added === 1 && !('catatan' in j.data.settings), 'visitor adds and gets public data only');
  assert((await vis({ action: 'delPenerima', ids: ['p4'] })).ok, 'visitor removes a wrong pupil');
  assert.strictEqual((await vis({ action: 'saveTable', table: 'tentatif', rows: [] })).error, 'PIN salah');

  await call({ action: 'setStatus', ids: ['p1'], status: 'Diterima' });
  j = await call({ action: 'setHadir', nama: ['SITI AMINAH'], hadir: true });
  assert(j.data.penerima.find((p) => p.id === 'p2').hadir && !j.data.penerima.find((p) => p.id === 'p1').hadir, 'only that pupil marked hadir');
  j = await call({ action: 'setHadir', nama: ['SITI AMINAH'], hadir: false });
  assert.strictEqual(j.data.penerima.find((p) => p.id === 'p2').hadir, '');
  await call({ action: 'setHadir', nama: ['ALI'], hadir: true });
  await call({ action: 'delPenerima', ids: ['p2'] });
  await call({ action: 'saveSettings', settings: { showNames: true, now: 1, bukan: 'x' } });
  let p = await pub();
  assert.deepStrictEqual([p.anugerah[0].n, p.anugerah[0].d], [1, 1]);
  assert.strictEqual(p.penerima.length, 1);
  assert(!('hadir' in p.penerima[0]), 'attendance hidden from public');
  assert.strictEqual(p.settings.now, 1);
  assert(!('bukan' in p.settings), 'unknown setting ignored');
  j = await call({ action: 'saveSettings', settings: { catatan: { kekuatan: 'Kerjasama baik', kelemahan: '', penambahbaikan: '' } } });
  assert.strictEqual(j.data.settings.catatan.kekuatan, 'Kerjasama baik');
  assert(!('catatan' in (await pub()).settings), 'Catatan Pengarah hidden from public');
  await call({ action: 'saveSettings', settings: { showNames: false } });
  assert.strictEqual((await pub()).penerima, null, 'names hidden from public');

  // galeri
  j = await call({ action: 'upload', purpose: 'galeri', name: 'x.png', mime: 'image/png', data: PNG, kat: 'Majlis', kapsyen: 'ujian' });
  assert.strictEqual(await status(j.item.src), 200);
  await call({ action: 'deletePhoto', id: j.item.id });
  assert.strictEqual(j.data.galeri.length, 1);
  assert.strictEqual((await pub()).galeri.length, 0);
  assert.notStrictEqual(await status(j.item.src), 200, 'file removed with the row');
  // foto AJK: a second upload for the same teacher replaces the first
  const a = await call({ action: 'upload', purpose: 'foto', nama: 'Harsidi Bin Junick', mime: 'image/png', data: PNG });
  const b = await call({ action: 'upload', purpose: 'foto', nama: 'Harsidi Bin Junick', replace: a.item.fid, mime: 'image/png', data: PNG });
  assert.strictEqual(b.data.fotoAjk.length, 1);
  assert.strictEqual(await status(b.data.fotoAjk[0].src), 200);
  assert.notStrictEqual(await status(a.item.src), 200, 'old photo removed');
  // logo
  j = await call({ action: 'upload', purpose: 'logo', name: 'logo.png', mime: 'image/png', data: PNG });
  assert.strictEqual(await status(j.data.settings.logo), 200);
  // bad input
  assert.match((await post({ action: 'upload', purpose: 'galeri', mime: 'text/html', data: PNG })).error, /JPEG/);
  assert.match((await post({ action: 'saveTable', table: 'galeri', rows: [] })).error, /tidak sah/);
  assert.match((await post({ action: 'apa' })).error, /tidak dikenali/);

  // tidy up
  for (const t of ['anugerah', 'tentatif']) await call({ action: 'saveTable', table: t, rows: [] });
  await call({ action: 'replacePenerima', anugerah: [], penerima: [] });
  console.log('test-supabase: semua lulus');
})().catch((e) => { console.error(e); process.exit(1); });
