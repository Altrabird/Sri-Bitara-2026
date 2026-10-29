/**
 * Majlis Anugerah Sri Bitara 2026 — SK Bandar Tawau
 * Backend Google Apps Script (Google Sheet = pangkalan data, Google Drive = galeri foto)
 *
 * CARA PASANG (ringkas — lihat PANDUAN-SETUP.md):
 *   1. script.google.com → Projek baharu → tampal fail ini.
 *   2. Tukar ADMIN_PIN di bawah kepada PIN 6 digit anda sendiri.
 *   3. Jalankan fungsi setup() sekali (benarkan akses).
 *   4. Deploy → New deployment → Web app → Execute as: Me, Who has access: Anyone.
 *   5. Salin URL /exec dan tampal ke API_URL dalam index.html.
 */
const ADMIN_PIN = 'TUKAR_PIN_INI';           // ← WAJIB tukar. Jangan kongsi PIN sebenar di GitHub.
const NAMA_FAIL = 'Data Majlis Sri Bitara 2026';
const NAMA_FOLDER = 'Galeri Sri Bitara 2026';
// Senarai murid (Hadir@SKBT). Akaun yang deploy skrip ini mesti boleh membuka sheet ini.
const ROSTER_ID = '1CiS8GhmhsDtOxZP0L3ZDmQDiA3DTbc1R0mQRQOfe1qY';
const ROSTER_GID = 237821847;

const TABLES = {
  anugerah:  ['id', 'kat', 'nama', 'sasaran'],   // sasaran kosong = tiada had penerima
  penerima:  ['id', 'aid', 'tahun', 'kelas', 'nama', 'catatan', 'status'],
  ajk:       ['id', 'jk', 'ahli', 'tugas'],
  tentatif:  ['id', 'masa', 'acara', 'pic'],
  persiapan: ['id', 'nama', 'peratus'],
  galeri:    ['id', 'fid', 'kat', 'kapsyen', 'masa']
};
const SET_DEFAULT = {
  nama: 'Majlis Anugerah Sri Bitara 2026', tagline: 'Meraikan kecemerlangan warga SK Bandar Tawau',
  tarikh: '2026-11-27', masa: '07:00', lokasi: 'Dewan SK Bandar Tawau',
  showNames: false, now: -1, logo: '', fotoFolder: '',
  catatan: { kekuatan: '', kelemahan: '', penambahbaikan: '' } // Catatan Pengarah: admin only, never in the public payload
};

/* ---------- HTTP ---------- */
function doGet(e) {
  try {
    const a = (e && e.parameter && e.parameter.action) || 'public';
    if (a === 'public') return out_(publicPayload_());
    return out_({ ok: false, error: 'Tindakan tidak dikenali' });
  } catch (err) { return out_({ ok: false, error: String(err.message || err) }); }
}

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (_) { return out_({ ok: false, error: 'Permintaan tidak sah' }); }
  try {
    checkPin_(req.pin);
    if (req.action === 'login') return out_({ ok: true });
    if (req.action === 'admin') return out_({ ok: true, data: allData_(), info: info_() });
    if (req.action === 'roster') return out_({ ok: true, roster: roster_() });
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try { return out_(Object.assign({ ok: true }, handle_(req))); }
    finally { lock.releaseLock(); }
  } catch (err) { return out_({ ok: false, error: String(err.message || err) }); }
}

function handle_(r) {
  let extra = {};
  switch (r.action) {
    case 'saveSettings': {
      const s = getSettings_();
      Object.keys(r.settings || {}).forEach(function (k) { if (k in SET_DEFAULT) s[k] = r.settings[k]; });
      writeSettings_(s);
      break;
    }
    case 'saveTable':
      if (!TABLES[r.table] || r.table === 'galeri') throw new Error('Jadual tidak sah');
      writeTable_(r.table, r.rows || []);
      break;
    case 'replacePenerima':
      writeTable_('anugerah', r.anugerah || []);
      writeTable_('penerima', r.penerima || []);
      break;
    case 'addPenerima': {
      const cur = readTable_('penerima');
      const have = {};
      cur.forEach(function (p) { have[p.aid + '|' + p.nama + '|' + p.kelas] = true; });
      const add = (r.rows || []).map(function (x) {
        const kelas = cell_(x.kelas).trim().toUpperCase();
        return { id: cell_(x.id), aid: cell_(x.aid), tahun: (kelas.match(/^(\d)/) || [])[1] || cell_(x.tahun), kelas: kelas,
          nama: cell_(x.nama).trim().toUpperCase().replace(/\s+/g, ' '), catatan: cell_(x.catatan).trim().toUpperCase(), status: '' };
      }).filter(function (x) { return x.id && x.aid && x.nama && !have[x.aid + '|' + x.nama + '|' + x.kelas]; });
      if (add.length) writeTable_('penerima', cur.concat(add));
      extra.added = add.length;
      break;
    }
    case 'delPenerima': {
      const del = {};
      (r.ids || []).forEach(function (id) { del[String(id)] = true; });
      writeTable_('penerima', readTable_('penerima').filter(function (p) { return !del[p.id]; }));
      break;
    }
    case 'setStatus':
      setStatus_(r.ids || [], r.status === 'Diterima' ? 'Diterima' : '');
      break;
    case 'upload':
      extra.item = upload_(r);
      break;
    case 'deletePhoto':
      deletePhoto_(r.id);
      break;
    default:
      throw new Error('Tindakan tidak dikenali');
  }
  CacheService.getScriptCache().remove('pub');
  extra.data = allData_();
  return extra;
}

function out_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

function checkPin_(pin) {
  if (!ADMIN_PIN || ADMIN_PIN === 'TUKAR_PIN_INI') throw new Error('PIN admin belum ditetapkan dalam Code.gs');
  const c = CacheService.getScriptCache();
  const fails = Number(c.get('fail') || 0);
  // shortcut: one global counter (GAS can't see client IPs) — a determined attacker can lock admins out for 10 min
  if (fails >= 10) throw new Error('Terlalu banyak cubaan salah. Cuba lagi selepas 10 minit.');
  if (String(pin || '') !== String(ADMIN_PIN)) { c.put('fail', String(fails + 1), 600); throw new Error('PIN salah'); }
}

/* ---------- data ---------- */
function publicPayload_() {
  const c = CacheService.getScriptCache();
  const hit = c.get('pub');
  if (hit) return JSON.parse(hit);
  const d = allData_();
  const cnt = {};
  d.penerima.forEach(function (p) {
    const k = cnt[p.aid] || (cnt[p.aid] = { n: 0, d: 0 });
    k.n++; if (p.status === 'Diterima') k.d++;
  });
  const settings = Object.assign({}, d.settings);
  delete settings.catatan;
  const pub = {
    ok: true, t: Date.now(), settings: settings,
    anugerah: d.anugerah.map(function (a) { const k = cnt[a.id] || { n: 0, d: 0 }; return { id: a.id, kat: a.kat, nama: a.nama, sasaran: a.sasaran, n: k.n, d: k.d }; }),
    penerima: d.settings.showNames ? d.penerima : null,
    ajk: d.ajk, fotoAjk: d.fotoAjk, tentatif: d.tentatif, persiapan: d.persiapan, galeri: d.galeri
  };
  try { c.put('pub', JSON.stringify(pub), 15); } catch (_) { /* >100KB: skip cache */ }
  return pub;
}

function allData_() {
  const d = { settings: getSettings_() };
  Object.keys(TABLES).forEach(function (t) { d[t] = readTable_(t); });
  d.fotoAjk = fotoAjk_(d.settings.fotoFolder);
  return d;
}

/* Foto AJK: setiap fail dalam folder dinamakan mengikut nama guru (cth. "Harsidi Bin Junick.jpg").
   Folder mesti dikongsi "Sesiapa yang ada pautan boleh lihat". Dicache 5 minit. */
function fotoAjk_(id) {
  if (!id) return [];
  const c = CacheService.getScriptCache(), key = 'foto|' + id;
  const hit = c.get(key);
  if (hit) return JSON.parse(hit);
  const out = [];
  try {
    const it = DriveApp.getFolderById(id).getFiles();
    while (it.hasNext()) {
      const f = it.next();
      if (!f.isTrashed() && /^image\//.test(f.getMimeType())) out.push({ n: f.getName().replace(/\.\w+$/, ''), fid: f.getId() });
    }
  } catch (_) { /* folder missing or no access: show initials */ }
  try { c.put(key, JSON.stringify(out), 300); } catch (_) { /* too big to cache */ }
  return out;
}

// the folder set in Tetapan, else a "Foto AJK" folder created inside the project's Drive folder
function fotoFolder_() {
  const s = getSettings_();
  if (s.fotoFolder) { try { return DriveApp.getFolderById(s.fotoFolder); } catch (_) { /* gone: recreate */ } }
  const f = folder_().createFolder('Foto AJK');
  s.fotoFolder = f.getId(); writeSettings_(s);
  return f;
}

function info_() {
  return { sheetUrl: ss_().getUrl(), folderUrl: folder_().getUrl() };
}

function ss_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('SS_ID');
  if (id) { try { return SpreadsheetApp.openById(id); } catch (_) { /* deleted: recreate */ } }
  const ss = SpreadsheetApp.create(NAMA_FAIL);
  props.setProperty('SS_ID', ss.getId());
  return ss;
}

function folder_() {
  const props = PropertiesService.getScriptProperties();
  const id = props.getProperty('FOLDER_ID');
  if (id) { try { return DriveApp.getFolderById(id); } catch (_) { /* deleted: recreate */ } }
  const f = DriveApp.createFolder(NAMA_FOLDER);
  props.setProperty('FOLDER_ID', f.getId());
  return f;
}

function sheet_(name, header) {
  const ss = ss_();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, header.length).setValues([header]);
  }
  return sh;
}

function cell_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'HH:mm');
  return v === null || v === undefined ? '' : String(v);
}

function readTable_(name) {
  const header = TABLES[name];
  const vals = sheet_(name, header).getDataRange().getValues();
  if (vals.length < 2) return [];
  const head = vals[0].map(String);
  return vals.slice(1).filter(function (r) { return r.some(function (v) { return v !== ''; }); }).map(function (r) {
    const o = {};
    header.forEach(function (k) { const i = head.indexOf(k); o[k] = i < 0 ? '' : cell_(r[i]); });
    return o;
  });
}

function writeTable_(name, rows) {
  const header = TABLES[name];
  const sh = sheet_(name, header);
  const vals = [header].concat(rows.map(function (r) { return header.map(function (k) { return cell_(r[k]); }); }));
  sh.clearContents();
  // '@' = plain text, so a value like "=IMPORTXML(...)" is stored as text, never run as a formula
  sh.getRange(1, 1, vals.length, header.length).setNumberFormat('@').setValues(vals);
}

function getSettings_() {
  const s = JSON.parse(JSON.stringify(SET_DEFAULT));
  const vals = sheet_('tetapan', ['kunci', 'nilai']).getDataRange().getValues();
  vals.slice(1).forEach(function (r) {
    const k = String(r[0]);
    if (!(k in SET_DEFAULT)) return;
    try { s[k] = JSON.parse(r[1]); } catch (_) { s[k] = cell_(r[1]); }
  });
  return s;
}

function writeSettings_(s) {
  const sh = sheet_('tetapan', ['kunci', 'nilai']);
  const vals = [['kunci', 'nilai']].concat(Object.keys(SET_DEFAULT).map(function (k) { return [k, JSON.stringify(s[k])]; }));
  sh.clearContents();
  sh.getRange(1, 1, vals.length, 2).setNumberFormat('@').setValues(vals);
}

function setStatus_(ids, status) {
  const sh = sheet_('penerima', TABLES.penerima);
  const vals = sh.getDataRange().getValues();
  const head = vals[0].map(String);
  const ci = head.indexOf('id'), si = head.indexOf('status');
  const want = {};
  ids.forEach(function (id) { want[String(id)] = true; });
  for (let i = 1; i < vals.length; i++) {
    if (want[String(vals[i][ci])]) sh.getRange(i + 1, si + 1).setValue(status);
  }
}

/* ---------- senarai murid (admin sahaja: mengandungi nama murid) ---------- */
function roster_() {
  const c = CacheService.getScriptCache();
  const hit = c.get('roster');
  if (hit) return JSON.parse(hit);
  let ss;
  try { ss = SpreadsheetApp.openById(ROSTER_ID); }
  catch (_) { throw new Error('Tiada akses ke Google Sheet senarai murid. Kongsi sheet itu (Viewer) dengan akaun yang deploy skrip ini.'); }
  const sh = ss.getSheets().filter(function (s) { return s.getSheetId() === ROSTER_GID; })[0] || ss.getSheetByName('Students') || ss.getSheets()[0];
  const v = sh.getDataRange().getValues();
  let hr = -1, ni = -1, ki = -1;
  for (let i = 0; i < Math.min(5, v.length) && hr < 0; i++) {
    const h = v[i].map(function (x) { return String(x).trim().toLowerCase(); });
    ni = h.findIndex(function (x) { return /^(nama|nama penuh|nama murid|name|student name|full name)$/.test(x); });
    ki = h.findIndex(function (x) { return /^(kelas|nama kelas|class|class name)$/.test(x); });
    if (ni >= 0 && ki >= 0) hr = i;
  }
  if (hr < 0) throw new Error('Lajur Nama / Kelas tidak dijumpai dalam sheet senarai murid');
  const norm = function (s) { return String(s).trim().toUpperCase().replace(/\s+/g, ' '); };
  const out = v.slice(hr + 1).map(function (r) { return { nama: norm(r[ni]), kelas: norm(r[ki]) }; })
    .filter(function (x) { return x.nama && x.kelas; });
  try { c.put('roster', JSON.stringify(out), 600); } catch (_) { /* too big to cache */ }
  return out;
}

/* ---------- galeri ---------- */
function upload_(r) {
  if (!/^image\/(jpeg|png|webp)$/.test(r.mime || '')) throw new Error('Hanya fail gambar JPEG/PNG/WebP');
  const bytes = Utilities.base64Decode(r.data || '');
  if (!bytes.length || bytes.length > 8 * 1024 * 1024) throw new Error('Saiz gambar tidak sah (maks 8MB)');
  const foto = r.purpose === 'foto';
  // foto AJK is named after the teacher so the web app can match it, e.g. "Harsidi Bin Junick.jpg"
  const nama = foto ? String(r.nama || '').replace(/[\\/:*?"<>|]/g, '').trim().slice(0, 80) : '';
  if (foto && !nama) throw new Error('Nama AJK tidak sah');
  const dest = foto ? fotoFolder_() : folder_();
  const file = dest.createFile(Utilities.newBlob(bytes, r.mime, foto ? nama + '.jpg' : String(r.name || 'foto').slice(0, 80)));
  try {
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  } catch (err) {
    file.setTrashed(true);
    throw new Error('Akaun Google ini tidak membenarkan perkongsian awam (pautan). Deploy skrip menggunakan akaun yang membenarkannya.');
  }
  if (r.purpose === 'logo') {
    const s = getSettings_(); s.logo = file.getId(); writeSettings_(s);
    return { fid: file.getId() };
  }
  if (foto) {
    // replace the teacher's old photo: same file name, or the file the app matched (r.replace)
    const it = dest.getFiles();
    while (it.hasNext()) {
      const f = it.next();
      if (f.getId() !== file.getId() && (f.getName().replace(/\.\w+$/, '') === nama || f.getId() === r.replace)) f.setTrashed(true);
    }
    CacheService.getScriptCache().remove('foto|' + dest.getId());
    return { fid: file.getId(), n: nama };
  }
  const item = { id: 'g' + Date.now().toString(36), fid: file.getId(), kat: String(r.kat || 'Majlis'), kapsyen: String(r.kapsyen || ''), masa: new Date().toISOString() };
  writeTable_('galeri', readTable_('galeri').concat([item]));
  return item;
}

function deletePhoto_(id) {
  const rows = readTable_('galeri');
  const hit = rows.filter(function (g) { return g.id === id; })[0];
  if (!hit) return;
  try { DriveApp.getFileById(hit.fid).setTrashed(true); } catch (_) { /* already gone */ }
  writeTable_('galeri', rows.filter(function (g) { return g.id !== id; }));
}

/* ---------- jalankan sekali dari editor ---------- */
function setup() {
  Object.keys(TABLES).forEach(function (t) { sheet_(t, TABLES[t]); });
  if (sheet_('tetapan', ['kunci', 'nilai']).getLastRow() < 2) writeSettings_(SET_DEFAULT);
  const def = ss_().getSheetByName('Sheet1') || ss_().getSheetByName('Helaian1');
  if (def && ss_().getSheets().length > 1) ss_().deleteSheet(def);
  Logger.log('Google Sheet: ' + ss_().getUrl());
  Logger.log('Folder galeri: ' + folder_().getUrl());
}
