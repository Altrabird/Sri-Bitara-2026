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

// setup() creates sheets and removes default Sheet1
makeGAS().ctx.setup();
console.log('backend: all tests passed');
