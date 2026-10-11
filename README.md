# Sri Bitara 2026

Web app for managing the **Majlis Anugerah Sri Bitara 2026** at SK Bandar Tawau: Dashboard, Anugerah, AJK, Tentatif, Galeri and an admin-only Tetapan, plus **Mod Pentas** (full-screen award reveal for the hall LCD).

- **Live:** https://altrabird.github.io/Sri-Bitara-2026/
- **Setup guide (Malay):** [PANDUAN-SETUP.md](PANDUAN-SETUP.md)

| File | Purpose |
|---|---|
| `index.html` | The whole app (vanilla HTML/CSS/JS, no build). Songket Diraja theme. Runs in demo mode (localStorage) until `API_URL` is set. |
| `Code.gs` | Google Apps Script backend: Google Sheet = database, Drive folder = gallery. PIN-protected writes. |
| `tests/gas-mock.js` | In-memory Apps Script services so the real `Code.gs` runs under Node. |
| `tests/test-backend.js` | Backend tests (`node tests/test-backend.js`). |
| `tests/e2e.py` | Playwright end-to-end tests, demo + remote mode (`python tests/e2e.py [awards.xlsx]`). |

No student data is stored in this repository. Recipient lists are imported in the browser from the school's Excel file and saved only to the school's Google Sheet.
