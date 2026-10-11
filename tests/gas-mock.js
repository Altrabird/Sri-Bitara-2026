// In-memory stand-ins for the Apps Script services Code.gs uses, so the REAL backend file runs locally.
// Usage: node tests/gas-mock.js [port]   → serves Code.gs as a web app (PIN 246810)
const fs = require('fs'), vm = require('vm'), http = require('http'), path = require('path');
const TEST_PIN = '246810';

const KLS = ['INOVATIF', 'INTELEK', 'KREATIF', 'KRITIS', 'PATRIOTIK'];
// fake Hadir@SKBT roster: header on row 2 (title row above), 3 pupils per class
const DEFAULT_ROSTER = [['Senarai Murid'], ['No', 'Name', 'Class', 'IC']].concat(
  [1, 2, 3, 4, 5, 6].flatMap(t => KLS.flatMap(k => [1, 2, 3].map(n => [n, `murid ${t}${k[0]}${k[1]} nombor ${n}`, `${t} ${k}`, '000000000000']))));

function makeGAS({ sharingBlocked = false, roster = DEFAULT_ROSTER, rosterAccess = true } = {}) {
  const props = {}, cache = {}, files = {}, folders = {}, sheets = {};
  let nid = 0, ss = null;
  class Range {
    constructor(sh, r, c, nr, nc) { Object.assign(this, { sh, r, c, nr, nc }); }
    setNumberFormat(f) { this.fmt = f; return this; }
    setValues(v) {
      v.forEach((row, i) => row.forEach((x, j) => {
        if (typeof x === 'string' && /^[=+]/.test(x) && this.fmt !== '@') throw new Error('formula would be evaluated: ' + x);
        this.sh.set(this.r + i, this.c + j, x);
      }));
      return this;
    }
    setValue(x) { this.sh.set(this.r, this.c, x); return this; }
    getValues() {
      return Array.from({ length: this.nr }, (_, i) => Array.from({ length: this.nc }, (_, j) => this.sh.get(this.r + i, this.c + j)));
    }
  }
  class Sheet {
    constructor(name, id = 0) { this.name = name; this.id = id; this.cells = []; }
    getSheetId() { return this.id; }
    set(r, c, v) { (this.cells[r - 1] = this.cells[r - 1] || [])[c - 1] = v; }
    get(r, c) { const v = (this.cells[r - 1] || [])[c - 1]; return v === undefined ? '' : v; }
    getLastRow() { return this.cells.length; }
    getDataRange() { return new Range(this, 1, 1, Math.max(1, this.cells.length), Math.max(1, ...this.cells.map(r => (r ? r.length : 0)))); }
    getRange(r, c, nr = 1, nc = 1) { return new Range(this, r, c, nr, nc); }
    clearContents() { this.cells = []; return this; }
  }
  const Spreadsheet = id => ({
    getId: () => id, getUrl: () => 'https://docs.google.com/spreadsheets/d/' + id,
    getSheetByName: n => sheets[n] || null,
    insertSheet: n => (sheets[n] = new Sheet(n)),
    getSheets: () => Object.values(sheets),
    deleteSheet: sh => { delete sheets[sh.name]; }
  });
  const ctx = {
    console, Date, JSON, String, Number, Object, Math, Error,
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] || null, setProperty: (k, v) => { props[k] = v; } }) },
    CacheService: { getScriptCache: () => ({
      get: k => (cache[k] ? cache[k] : null),
      put: (k, v) => { if (v.length > 100000) throw new Error('Argument too large'); cache[k] = v; },
      remove: k => { delete cache[k]; }
    }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    SpreadsheetApp: {
      create: () => { sheets.Sheet1 = new Sheet('Sheet1'); return (ss = Spreadsheet('ss' + ++nid)); },
      openById: id => {
        if (id === '1CiS8GhmhsDtOxZP0L3ZDmQDiA3DTbc1R0mQRQOfe1qY' && rosterAccess) {
          const other = new Sheet('Lain', 1), sh = new Sheet('Murid', 237821847);
          roster.forEach((r, i) => r.forEach((v, j) => sh.set(i + 1, j + 1, v)));
          return { getSheets: () => [other, sh], getSheetByName: () => null };
        }
        if (!ss || ss.getId() !== id) throw new Error('not found');
        return ss;
      }
    },
    DriveApp: {
      Access: { ANYONE_WITH_LINK: 'ANYONE_WITH_LINK' }, Permission: { VIEW: 'VIEW' },
      createFolder: name => {
        const id = 'fo' + ++nid;
        return (folders[id] = { getId: () => id, getUrl: () => 'https://drive.google.com/drive/folders/' + id, createFile: blob => {
          const fid = 'fi' + ++nid;
          return (files[fid] = { blob, trashed: false, shared: false, getId: () => fid,
            setSharing() { if (sharingBlocked) throw new Error('Sharing blocked by domain'); this.shared = true; },
            setTrashed(t) { this.trashed = t; } });
        } });
      },
      getFolderById: id => { if (!folders[id]) throw new Error('no folder'); return folders[id]; },
      getFileById: id => { if (!files[id]) throw new Error('no file'); return files[id]; }
    },
    Utilities: {
      base64Decode: s => [...Buffer.from(s, 'base64')],
      newBlob: (bytes, mime, name) => ({ bytes, mime, name }),
      formatDate: d => d.toISOString().slice(11, 16)
    },
    Session: { getScriptTimeZone: () => 'Asia/Kuching' },
    ContentService: {
      MimeType: { JSON: 'json' },
      createTextOutput: s => ({ s, setMimeType() { return this; }, getContent() { return this.s; } })
    },
    Logger: { log: () => {} }
  };
  const code = fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8')
    .replace(/const ADMIN_PIN = '[^']*';/, `const ADMIN_PIN = '${TEST_PIN}';`);
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  const get = params => JSON.parse(ctx.doGet({ parameter: params || {} }).getContent());
  const post = body => JSON.parse(ctx.doPost({ postData: { contents: JSON.stringify(body) } }).getContent());
  return { ctx, get, post, sheets, files, cache, props };
}

function serve(port) {
  const g = makeGAS();
  http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Content-Type', 'application/json');
    if (req.method === 'GET') {
      const q = Object.fromEntries(new URL(req.url, 'http://x').searchParams);
      return res.end(JSON.stringify(g.get(q)));
    }
    let body = '';
    req.on('data', c => (body += c));
    req.on('end', () => res.end(JSON.stringify(g.post(JSON.parse(body)))));
  }).listen(port, () => console.log('gas-mock listening on ' + port));
}

module.exports = { makeGAS, TEST_PIN };
if (require.main === module) serve(+process.argv[2] || 8787);
