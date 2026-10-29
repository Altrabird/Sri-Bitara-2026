// Runs the real Code.gs against in-memory mocks. Usage: node tests/test-backend.js
const assert = require('assert');
const { makeGAS, TEST_PIN: PIN } = require('./gas-mock');

let g = makeGAS();
// empty DB → public payload works
let pub = g.get();
assert.ok(pub.ok && pub.anugerah.length === 0 && pub.penerima === null, 'empty public');

// PIN
assert.strictEqual(g.post({ action: 'login', pin: '000000' }).error, 'PIN salah');
assert.ok(g.post({ action: 'login', pin: PIN }).ok);
for (let i = 0; i < 10; i++) g.post({ action: 'login', pin: 'x' });
assert.match(g.post({ action: 'login', pin: PIN }).error, /Terlalu banyak/, 'lockout after 10 fails');
g = makeGAS();

// tables + formula safety
let r = g.post({ action: 'saveTable', pin: PIN, table: 'anugerah', rows: [{ id: 'a1', kat: 'K', nama: 'Anugerah Sains' }, { id: 'a2', kat: 'H', nama: '=IMPORTXML("http://x")' }] });
assert.ok(r.ok, r.error);
assert.strictEqual(r.data.anugerah[1].nama, '=IMPORTXML("http://x")', 'formula-looking text stored as text');
assert.strictEqual(g.post({ action: 'saveTable', pin: PIN, table: 'galeri', rows: [] }).error, 'Jadual tidak sah');
assert.strictEqual(g.post({ action: 'saveTable', pin: PIN, table: 'nope', rows: [] }).error, 'Jadual tidak sah');

// recipients + status + counts
r = g.post({ action: 'replacePenerima', pin: PIN,
  anugerah: [{ id: 'a1', kat: 'K', nama: 'Anugerah Sains' }],
  penerima: [1, 2, 3].map(i => ({ id: 'r' + i, aid: 'a1', tahun: '6', kelas: '6 INOVATIF', nama: 'MURID ' + i, catatan: '', status: '' })) });
assert.ok(r.ok, r.error);
assert.ok(g.post({ action: 'setStatus', pin: PIN, ids: ['r2'], status: 'Diterima' }).ok);
pub = g.get();
assert.deepStrictEqual([pub.anugerah[0].n, pub.anugerah[0].d], [3, 1], 'counts');
assert.strictEqual(pub.penerima, null, 'names hidden by default');

// settings: whitelist + showNames + cache invalidation
r = g.post({ action: 'saveSettings', pin: PIN, settings: { showNames: true, now: 3, evil: 'x', nama: 'Majlis Ujian' } });
assert.ok(r.ok, r.error);
pub = g.get();
assert.strictEqual(pub.settings.showNames, true);
assert.strictEqual(pub.settings.now, 3);
assert.strictEqual(pub.settings.nama, 'Majlis Ujian');
assert.ok(!('evil' in pub.settings), 'unknown settings ignored');
// Catatan Pengarah: saved for admin, never public
r = g.post({ action: 'saveSettings', pin: PIN, settings: { catatan: { kekuatan: 'Kerjasama baik', kelemahan: 'Raptai lewat', penambahbaikan: '' } } });
assert.strictEqual(r.data.settings.catatan.kelemahan, 'Raptai lewat');
assert.ok(!('catatan' in g.get().settings), 'catatan hidden from public');
assert.strictEqual(pub.penerima.length, 3, 'names visible when showNames');
assert.strictEqual(pub.penerima.find(p => p.id === 'r2').status, 'Diterima');

// admin payload always has names
assert.strictEqual(g.post({ action: 'admin', pin: PIN }).data.penerima.length, 3);

// galeri upload + delete
const jpg = Buffer.from([0xff, 0xd8, 0xff, 0xd9]).toString('base64');
assert.match(g.post({ action: 'upload', pin: PIN, mime: 'text/html', data: jpg }).error, /Hanya fail gambar/);
r = g.post({ action: 'upload', pin: PIN, mime: 'image/jpeg', data: jpg, name: 'a.jpg', kat: 'Majlis', kapsyen: 'Ujian' });
assert.ok(r.ok, r.error);
assert.ok(g.files[r.item.fid].shared, 'file shared by link');
assert.strictEqual(g.get().galeri.length, 1);
assert.ok(g.post({ action: 'deletePhoto', pin: PIN, id: r.item.id }).ok);
assert.strictEqual(g.get().galeri.length, 0);
assert.ok(g.files[r.item.fid].trashed, 'deleted photo trashed');

// logo upload goes to settings, not galeri
r = g.post({ action: 'upload', pin: PIN, mime: 'image/png', data: jpg, purpose: 'logo' });
assert.ok(r.ok && g.get().settings.logo === r.item.fid && g.get().galeri.length === 0, 'logo');

// domain blocks public sharing → clear error, file trashed
const blocked = makeGAS({ sharingBlocked: true });
r = blocked.post({ action: 'upload', pin: PIN, mime: 'image/jpeg', data: jpg });
assert.match(r.error, /tidak membenarkan perkongsian/);
assert.ok(Object.values(blocked.files).every(f => f.trashed));

// big payload (>100KB) still served when cache refuses it
const many = Array.from({ length: 1500 }, (_, i) => ({ id: 'r' + i, aid: 'a1', tahun: '5', kelas: '5 KREATIF', nama: 'NAMA MURID YANG PANJANG NOMBOR ' + i, catatan: '', status: '' }));
g.post({ action: 'replacePenerima', pin: PIN, anugerah: [{ id: 'a1', kat: 'K', nama: 'X' }], penerima: many });
pub = g.get();
assert.ok(pub.ok && pub.penerima.length === 1500, 'large payload');

// roster: right tab by gid, header found below a title row, IC column never returned
g = makeGAS();
assert.match(g.get({ action: 'roster' }).error || '', /tidak dikenali/, 'roster not public via GET');
assert.strictEqual(g.post({ action: 'roster', pin: 'x' }).error, 'PIN salah');
r = g.post({ action: 'roster', pin: PIN });
assert.ok(r.ok, r.error);
assert.strictEqual(r.roster.length, 90);
assert.deepStrictEqual(Object.keys(r.roster[0]).sort(), ['kelas', 'nama']);
assert.deepStrictEqual(r.roster[0], { nama: 'MURID 1IN NOMBOR 1', kelas: '1 INOVATIF' });
assert.match(makeGAS({ rosterAccess: false }).post({ action: 'roster', pin: PIN }).error, /Tiada akses/);
assert.match(makeGAS({ roster: [['A', 'B']] }).post({ action: 'roster', pin: PIN }).error, /tidak dijumpai/);

// add / delete single recipients (duplicates skipped, tahun from kelas)
g.post({ action: 'saveTable', pin: PIN, table: 'anugerah', rows: [{ id: 'a1', kat: 'K', nama: 'Sains' }] });
r = g.post({ action: 'addPenerima', pin: PIN, rows: [
  { id: 'r1', aid: 'a1', kelas: '4 kreatif', nama: ' murid  satu ', catatan: '' },
  { id: 'r2', aid: 'a1', kelas: '4 KREATIF', nama: 'MURID DUA' }] });
assert.ok(r.ok && r.added === 2, r.error);
assert.deepStrictEqual([r.data.penerima[0].nama, r.data.penerima[0].kelas, r.data.penerima[0].tahun], ['MURID SATU', '4 KREATIF', '4']);
r = g.post({ action: 'addPenerima', pin: PIN, rows: [{ id: 'r3', aid: 'a1', kelas: '4 KREATIF', nama: 'MURID SATU' }] });
assert.strictEqual(r.added, 0, 'duplicate skipped');
r = g.post({ action: 'delPenerima', pin: PIN, ids: ['r1'] });
assert.deepStrictEqual(r.data.penerima.map(p => p.id), ['r2']);

// anugerah sasaran round-trips to the public payload; blank = unlimited
g = makeGAS();
g.post({ action: 'saveTable', pin: PIN, table: 'anugerah', rows: [{ id: 'a1', kat: 'K', nama: 'Sains', sasaran: '12' }, { id: 'a2', kat: 'K', nama: 'NILAM' }] });
assert.deepStrictEqual(g.get().anugerah.map(a => a.sasaran), ['12', ''], 'sasaran');

// foto AJK: images in the chosen folder are listed by name; a bad folder just gives none
assert.deepStrictEqual(g.get().fotoAjk, [], 'no folder set');
const fo = g.ctx.DriveApp.createFolder('Foto AJK');
fo.createFile({ name: 'Harsidi Bin Junick.jpg', mime: 'image/jpeg' });
fo.createFile({ name: 'nota.pdf', mime: 'application/pdf' });
g.post({ action: 'saveSettings', pin: PIN, settings: { fotoFolder: fo.getId() } });
assert.deepStrictEqual(g.get().fotoAjk.map(f => f.n), ['Harsidi Bin Junick'], 'foto listed, non-image skipped');
g.post({ action: 'saveSettings', pin: PIN, settings: { fotoFolder: 'tiada' } });
assert.deepStrictEqual(g.get().fotoAjk, [], 'missing folder → initials');

// foto AJK from the app's cropper: folder made on first upload, named after the teacher, old photo replaced
g = makeGAS();
r = g.post({ action: 'upload', pin: PIN, purpose: 'foto', nama: 'Harsidi Bin Junick', mime: 'image/jpeg', data: jpg });
assert.ok(r.ok, r.error);
const fotoDir = g.get().settings.fotoFolder;
assert.ok(fotoDir, 'Foto AJK folder created and saved in settings');
assert.deepStrictEqual(g.get().fotoAjk.map(f => f.n), ['Harsidi Bin Junick']);
assert.ok(g.files[r.item.fid].shared, 'photo shared by link');
const old = r.item.fid;
r = g.post({ action: 'upload', pin: PIN, purpose: 'foto', nama: 'Harsidi Bin Junick', mime: 'image/jpeg', data: jpg });
assert.ok(g.files[old].trashed && g.get().fotoAjk.length === 1 && g.get().fotoAjk[0].fid === r.item.fid, 'old photo replaced');
assert.strictEqual(g.get().settings.fotoFolder, fotoDir, 'same folder reused');
assert.match(g.post({ action: 'upload', pin: PIN, purpose: 'foto', nama: ' / ', mime: 'image/jpeg', data: jpg }).error, /Nama AJK/);

// setup() creates sheets and removes default Sheet1
makeGAS().ctx.setup();
console.log('backend: all tests passed');
