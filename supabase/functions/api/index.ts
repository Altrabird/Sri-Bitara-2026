/**
 * Majlis Anugerah Sri Bitara 2026 — backend Supabase (ganti Code.gs).
 * Protokol sama seperti Code.gs: GET ?action=public, POST {action, pin, ...} → JSON {ok, ...}.
 * Pangkalan data: jadual Postgres (supabase/schema.sql). Foto: bucket awam "foto".
 * Deploy dengan verify_jwt = false: fungsi ini menyemak PIN sendiri.
 */
import { createClient } from 'npm:@supabase/supabase-js@2.45.4';

const SB_URL = Deno.env.get('SUPABASE_URL')!;
const db = createClient(SB_URL, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!);
const REF = new URL(SB_URL).hostname.split('.')[0];
// Senarai murid (Hadir@SKBT) masih dibaca oleh Code.gs kerana ia Google Sheet sekolah, menggunakan admin.pin_gas (= ADMIN_PIN Code.gs).
const GAS_URL = 'https://script.google.com/macros/s/AKfycbwh54z1yrC5Z5KKIleEUGjMedFaNQ0Bt6yL5-tmx0_Qq8_voqOa1ZHZl0w0mPHVwfU5Jg/exec';

const TABLES: Record<string, string[]> = {
  anugerah:  ['id', 'kat', 'nama', 'sasaran'],
  penerima:  ['id', 'aid', 'tahun', 'kelas', 'nama', 'catatan', 'status', 'hadir'],
  ajk:       ['id', 'jk', 'ahli', 'tugas'],
  tentatif:  ['id', 'masa', 'acara', 'pic'],
  persiapan: ['id', 'nama', 'peratus'],
  galeri:    ['id', 'fid', 'kat', 'kapsyen', 'masa']
};
const SET_DEFAULT: Record<string, unknown> = {
  nama: 'Majlis Anugerah Sri Bitara 2026', tagline: 'Meraikan kecemerlangan warga SK Bandar Tawau',
  tarikh: '2026-11-27', masa: '07:00', lokasi: 'Dewan SK Bandar Tawau',
  showNames: false, now: -1, logo: '',
  catatan: { kekuatan: '', kelemahan: '', penambahbaikan: '' } // Catatan Pengarah: admin only, never in the public payload
};
const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'content-type' };
const MIME_EXT: Record<string, string> = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' };

/* ---------- HTTP ---------- */
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  try {
    if (req.method === 'GET') {
      const a = new URL(req.url).searchParams.get('action') || 'public';
      return out(a === 'public' ? await publicPayload() : { ok: false, error: 'Tindakan tidak dikenali' });
    }
    let r;
    try { r = JSON.parse(await req.text()); } catch { return out({ ok: false, error: 'Permintaan tidak sah' }); }
    // owner's choice (2026-10-29): Anugerah needs no PIN (pick, add, remove pupils, tick Diterima); Tetapan still does.
    // An empty PIN is never checked, so visitors don't count as failed tries and lock the admin out.
    const open = ['roster', 'addPenerima', 'delPenerima', 'setStatus'].includes(r.action);
    if (!open || r.pin) await checkPin(r.pin);
    if (r.action === 'login') return out({ ok: true });
    if (r.action === 'admin') return out({ ok: true, data: await allData(), info: info() });
    if (r.action === 'roster') return out({ ok: true, roster: await roster(r.pin) });
    const res = await handle(r);
    if (!r.pin) res.data = await publicPayload(); // no attendance or Catatan Pengarah for visitors
    return out({ ok: true, ...res });
  } catch (err) {
    return out({ ok: false, error: String((err as Error).message || err) });
  }
});

async function handle(r: any) {
  const extra: Record<string, unknown> = {};
  switch (r.action) {
    case 'saveSettings': {
      const rows = Object.keys(r.settings || {}).filter((k) => k in SET_DEFAULT).map((k) => ({ kunci: k, nilai: r.settings[k] }));
      if (rows.length) await q(db.from('tetapan').upsert(rows));
      break;
    }
    case 'saveTable':
      if (!TABLES[r.table] || r.table === 'galeri') throw new Error('Jadual tidak sah');
      await writeTable(r.table, r.rows || []);
      break;
    case 'replacePenerima':
      await writeTable('anugerah', r.anugerah || []);
      await writeTable('penerima', r.penerima || []);
      break;
    case 'addPenerima': {
      const rows = (r.rows || []).map((x: any) => {
        const kelas = cell(x.kelas).trim().toUpperCase();
        return { id: cell(x.id), aid: cell(x.aid), tahun: (kelas.match(/^(\d)/) || [])[1] || cell(x.tahun), kelas,
          nama: cell(x.nama).trim().toUpperCase().replace(/\s+/g, ' '), catatan: cell(x.catatan).trim().toUpperCase(), status: '' };
      });
      const aids = [...new Set(rows.map((x: any) => x.aid))];
      // shortcut: no lock as in Code.gs — two admins adding the same pupil at the same second can both succeed
      const cur = aids.length ? await q(db.from('penerima').select('aid,nama,kelas').in('aid', aids)) : [];
      const have = new Set(cur.map((p: any) => p.aid + '|' + p.nama + '|' + p.kelas));
      const add = rows.filter((x: any) => x.id && x.aid && x.nama && !have.has(x.aid + '|' + x.nama + '|' + x.kelas));
      if (add.length) await q(db.from('penerima').insert(add));
      extra.added = add.length;
      break;
    }
    case 'delPenerima':
      await q(db.from('penerima').delete().in('id', (r.ids || []).map(String)));
      break;
    case 'setStatus':
      await q(db.from('penerima').update({ status: r.status === 'Diterima' ? 'Diterima' : '' }).in('id', (r.ids || []).map(String)));
      break;
    case 'setHadir': // one pupil can hold several awards: mark every row with that name
      await q(db.from('penerima').update({ hadir: r.hadir ? new Date().toISOString() : '' }).in('nama', (r.nama || []).map(String)));
      break;
    case 'upload':
      extra.item = await upload(r);
      break;
    case 'deletePhoto': {
      const hit = (await q(db.from('galeri').select('fid').eq('id', cell(r.id))))[0];
      if (hit) {
        await db.storage.from('foto').remove([hit.fid]);
        await q(db.from('galeri').delete().eq('id', cell(r.id)));
      }
      break;
    }
    default:
      throw new Error('Tindakan tidak dikenali');
  }
  extra.data = await allData();
  return extra;
}

function out(o: unknown) {
  return new Response(JSON.stringify(o), { headers: { ...CORS, 'Content-Type': 'application/json' } });
}

async function checkPin(pin: unknown) {
  const s = await q(db.rpc('semak_pin', { p: String(pin ?? '') }));
  if (s === 'ok') return;
  if (s === 'kunci') throw new Error('Terlalu banyak cubaan salah. Cuba lagi selepas 10 minit.');
  if (s === 'tiada') throw new Error('PIN admin belum ditetapkan (jadual admin)');
  throw new Error('PIN salah');
}

// throws the database error instead of returning it, so every failed write reaches the user as an error
async function q(p: PromiseLike<{ data: any; error: any }>) {
  const { data, error } = await p;
  if (error) throw new Error(error.message);
  return data;
}

const cell = (v: unknown) => (v === null || v === undefined ? '' : String(v));
const pub = (path: string) => `${SB_URL}/storage/v1/object/public/foto/${path}`;

/* ---------- data ---------- */
async function publicPayload() {
  const d = await allData();
  const cnt: Record<string, { n: number; d: number }> = {};
  d.penerima.forEach((p: any) => {
    const k = cnt[p.aid] || (cnt[p.aid] = { n: 0, d: 0 });
    k.n++; if (p.status === 'Diterima') k.d++;
  });
  const { catatan: _c, ...settings } = d.settings;
  return {
    ok: true, t: Date.now(), settings,
    anugerah: d.anugerah.map((a: any) => ({ ...a, ...(cnt[a.id] || { n: 0, d: 0 }) })),
    penerima: d.settings.showNames ? d.penerima.map(({ hadir: _, ...p }: any) => p) : null, // attendance stays admin-only
    ajk: d.ajk, fotoAjk: d.fotoAjk, tentatif: d.tentatif, persiapan: d.persiapan, galeri: d.galeri
  };
}

// same shape as Code.gs; photos carry src (public Storage URL), which index.html prefers over Drive ids
async function allData() {
  const d = await q(db.rpc('semua_data'));
  d.settings = { ...SET_DEFAULT, ...d.tetapan };
  delete d.tetapan;
  d.galeri.forEach((g: any) => (g.src = pub(g.fid)));
  d.fotoAjk.forEach((f: any) => (f.src = pub(f.fid)));
  return d;
}

function info() {
  return { sheetUrl: `https://supabase.com/dashboard/project/${REF}/editor`, folderUrl: `https://supabase.com/dashboard/project/${REF}/storage/buckets/foto` };
}

async function writeTable(t: string, rows: any[]) {
  const header = TABLES[t];
  await q(db.rpc('ganti_jadual', { t, r: rows.map((x) => Object.fromEntries(header.map((k) => [k, cell(x[k])]))) }));
}

/* ---------- senarai murid (admin sahaja: mengandungi nama murid) ---------- */
declare const EdgeRuntime: { waitUntil(p: Promise<unknown>): void };

// Apps Script takes 2+ s, so answer from the saved copy and refresh it after replying when it is over 10 minutes old
async function roster(pin: unknown) {
  const c = (await q(db.from('murid_cache').select('roster,masa').eq('id', 1)))[0];
  if (!c) return await rosterGas(pin);
  if (Date.now() - Date.parse(c.masa) > 10 * 60 * 1000) EdgeRuntime.waitUntil(rosterGas(pin).catch((e) => console.error('roster', e)));
  return c.roster;
}

async function rosterGas(pin: unknown) {
  const p = (await q(db.from('admin').select('pin_gas').eq('id', 1)))[0]?.pin_gas || pin;
  const j = await (await fetch(GAS_URL, { method: 'POST', body: JSON.stringify({ action: 'roster', pin: p }) })).json();
  if (!j.ok) throw new Error(j.error === 'PIN salah' ? 'PIN Apps Script salah: isi admin.pin_gas di Supabase dengan ADMIN_PIN dalam Code.gs.' : j.error);
  await q(db.from('murid_cache').upsert({ id: 1, roster: j.roster, masa: new Date().toISOString() }));
  return j.roster;
}

/* ---------- foto ---------- */
async function upload(r: any) {
  const ext = MIME_EXT[r.mime];
  if (!ext) throw new Error('Hanya fail gambar JPEG/PNG/WebP');
  let bytes: Uint8Array;
  try { bytes = Uint8Array.from(atob(r.data || ''), (c) => c.charCodeAt(0)); } catch { throw new Error('Gambar tidak sah'); }
  if (!bytes.length || bytes.length > 8 * 1024 * 1024) throw new Error('Saiz gambar tidak sah (maks 8MB)');
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const foto = r.purpose === 'foto';
  // foto AJK is matched by the teacher's name, e.g. "Harsidi Bin Junick"
  const nama = foto ? cell(r.nama).replace(/[\\/:*?"<>|]/g, '').trim().slice(0, 80) : '';
  if (foto && !nama) throw new Error('Nama AJK tidak sah');
  const path = `${r.purpose === 'logo' ? 'logo' : foto ? 'ajk' : 'galeri'}/${id}.${ext}`;
  await q(db.storage.from('foto').upload(path, bytes, { contentType: r.mime, cacheControl: '31536000' }));
  try {
    if (r.purpose === 'logo') {
      const old = (await q(db.from('tetapan').select('nilai').eq('kunci', 'logo')))[0]?.nilai;
      await q(db.from('tetapan').upsert({ kunci: 'logo', nilai: pub(path) }));
      if (typeof old === 'string' && old.startsWith(pub(''))) await db.storage.from('foto').remove([old.slice(pub('').length)]);
      return { fid: path };
    }
    if (foto) {
      // replace the teacher's old photo: same name, or the file the app matched (r.replace)
      const old = await q(db.from('foto_ajk').select('n,fid').or(`n.eq.${JSON.stringify(nama)},fid.eq.${JSON.stringify(cell(r.replace))}`));
      if (old.length) {
        await q(db.from('foto_ajk').delete().in('n', old.map((o: any) => o.n)));
        await db.storage.from('foto').remove(old.map((o: any) => o.fid));
      }
      await q(db.from('foto_ajk').insert({ n: nama, fid: path }));
      return { fid: path, n: nama, src: pub(path) };
    }
    const item = { id: 'g' + id, fid: path, kat: cell(r.kat || 'Majlis'), kapsyen: cell(r.kapsyen), masa: new Date().toISOString() };
    await q(db.from('galeri').insert(item));
    return { ...item, src: pub(path) };
  } catch (err) {
    await db.storage.from('foto').remove([path]); // don't leave an orphan file when the row fails
    throw err;
  }
}
