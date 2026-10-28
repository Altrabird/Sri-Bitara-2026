"""Salin data dari backend Google Apps Script (Sheet + logo Drive) ke backend Supabase. MENGGANTIKAN data Supabase.
Boleh dijalankan semula sebelum bertukar. Perlu "Papar nama penerima" dihidupkan di laman lama (penerima dibaca dari data awam).
Usage: python tools/gs_ke_supabase.py <gas-exec-url> <supabase-api-url> <pin-supabase>"""
import base64, json, sys, urllib.request

GAS, SB, PIN = sys.argv[1:4]


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read(), r.headers.get_content_type()


def call(action, **kw):
    req = urllib.request.Request(SB, json.dumps({'action': action, 'pin': PIN, **kw}).encode(), {'Content-Type': 'text/plain;charset=utf-8'})
    with urllib.request.urlopen(req, timeout=120) as r:
        j = json.load(r)
    if not j.get('ok'):
        sys.exit(f'{action}: {j.get("error")}')
    return j


d = json.loads(get(GAS + '?action=public')[0])
if d.get('penerima') is None:
    sys.exit('Penerima tersembunyi dalam data awam: hidupkan "Papar nama penerima" di laman lama dahulu.')
if d.get('galeri') or d.get('fotoAjk'):
    sys.exit(f'Ada {len(d.get("galeri") or [])} foto galeri / {len(d.get("fotoAjk") or [])} foto AJK di Drive: skrip ini belum menyalin foto tersebut.')

call('replacePenerima', anugerah=d['anugerah'], penerima=d['penerima'])
for t in ['ajk', 'tentatif', 'persiapan']:
    call('saveTable', table=t, rows=d[t])
s = d['settings']
call('saveSettings', settings={k: v for k, v in s.items() if k not in ('logo', 'fotoFolder')})
if s.get('logo') and not s['logo'].startswith('http'):
    img, mime = get(f'https://drive.google.com/thumbnail?id={s["logo"]}&sz=w400')
    call('upload', purpose='logo', name='logo', mime=mime, data=base64.b64encode(img).decode())

n = call('admin')['data']
print({k: len(n[k]) for k in ['anugerah', 'penerima', 'ajk', 'tentatif', 'persiapan', 'galeri']}, 'logo:', n['settings']['logo'] or '-')
