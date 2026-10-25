# Panduan Setup: Sri Bitara 2026

Aplikasi pengurusan **Majlis Anugerah Sri Bitara 2026, SK Bandar Tawau**.
Tanpa backend, aplikasi berjalan dalam **Mod Demo** (data hanya dalam pelayar itu sahaja, PIN demo `123456`).
Ikut langkah 1 hingga 3 sekali sahaja supaya semua telefon dan LCD berkongsi data yang sama.

---

## 1. Pasang backend (Google Apps Script), lebih kurang 10 minit

1. Buka **https://script.google.com**, kemudian klik **Projek baharu**.
2. Padam kod contoh. Salin **semua** isi fail `Code.gs` dan tampal.
3. Di baris atas, tukar `TUKAR_PIN_INI` kepada **PIN admin** anda (sekurang-kurangnya 4 aksara, nombor atau huruf; huruf besar/kecil dibezakan)
   > PIN ini hanya ada dalam skrip Google anda. Jangan tampal PIN sebenar ke GitHub.
4. Klik **Simpan**. Pilih fungsi **`setup`** di menu atas, kemudian klik **Jalankan** dan benarkan akses (*Review permissions → Allow*).
   Google Sheet **"Data Majlis Sri Bitara 2026"** dan folder **"Galeri Sri Bitara 2026"** akan dicipta dalam Drive anda.
5. Klik **Deploy → New deployment → ⚙ Web app**:
   - *Execute as*: **Me**
   - *Who has access*: **Anyone**
6. Klik **Deploy** dan salin **Web app URL** (berakhir dengan `/exec`).

> ⚠️ **Akaun DELIMa (moe-dl.edu.my):** sesetengah domain sekolah menyekat perkongsian fail kepada umum. Jika muat naik foto memaparkan ralat *"tidak membenarkan perkongsian awam"*, deploy semula skrip menggunakan **akaun Gmail peribadi**.

## 2. Sambungkan aplikasi ke backend

Tampal URL `/exec` ke dalam `index.html` di baris ini:

```js
const API_URL = ''; // ← tampal URL Web App ...
```

Kemudian *commit* dan *push*. (Atau hantar URL kepada pembangun untuk dikemas kini.)

Untuk cuba tanpa mengubah fail, buka: `https://altrabird.github.io/Sri-Bitara-2026/?api=URL_EXEC_ANDA`

## 3. Log masuk admin kali pertama

1. Buka aplikasi dan pergi ke **Tetapan**. Masukkan PIN admin.
2. Aplikasi akan bertanya sama ada mahu mengisi **data permulaan**. Pilih **OK**. Ini mengisi 23 kategori anugerah, 23 AJK, tentatif draf dan senarai persiapan.
3. Di **Tetapan → Maklumat Majlis**, sahkan tarikh, masa dan lokasi, muat naik logo sekolah, kemudian klik **Simpan**.

---

## Kegunaan harian

| Tugas | Di mana |
|---|---|
| Import senarai penerima 2026 | **Tetapan → Import Penerima**. Pilih fail Excel (format sama seperti 2025), semak kategori, kemudian klik **Gantikan semua**. Helaian senarai murid/IC diabaikan dan **tidak** dimuat naik. |
| **Tambah penerima satu per satu** | **Anugerah**, buka kad anugerah, kemudian di **Tambah Penerima**: (1) pilih **kelas**, (2) tandakan murid, kemudian klik **Tambah**. Senarai murid diambil dari Google Sheet Hadir@SKBT. Murid tiada dalam senarai boleh ditaip di ruang *Nama lain*. Butang 🗑 memadam penerima. |
| **Murid menerima lebih daripada 1 anugerah** | **Anugerah → Senarai Murid**. Semua penerima disusun ikut murid, bersama bilangan dan senarai anugerah masing-masing. Tapis ikut kelas atau kategori, togol *Hanya > 1 anugerah*, dan muat turun CSV. Tanda ⚠ bermaksud nama yang sama tersenarai dengan kelas berbeza dalam Excel; sila semak. |
| Papar nama penerima kepada umum | **Tetapan → Maklumat Majlis**, togol *Papar nama penerima*. Jika DIMATIKAN, umum hanya nampak bilangan penerima. |
| Kemas kini AJK / Tentatif / % Persiapan | Tab masing-masing dalam **Tetapan**. Untuk AJK, tulis satu nama setiap baris dan tambah **(K)** untuk Ketua. |
| Muat turun senarai penerima (CSV) | **Tetapan → Import Penerima → CSV** (untuk JK Sijil / JK Pengurus Penerima) |
| Betulkan nama murid satu per satu | **Tetapan → Sistem → Buka Sheet**, edit terus dalam Google Sheet (tab `penerima`) |
| Muat naik foto | **Galeri**. Bila mod admin dibuka, kotak muat naik muncul. Seret foto atau klik **Pilih**. |

## Hari majlis

**Laptop LCD (JK Penerima Anugerah / Slaid)**
1. Buka aplikasi, masukkan PIN di Tetapan, kemudian klik **MOD PENTAS** (atau **Tayang di Mod Pentas** dari kad anugerah).
2. Pilih anugerah dan tahun. Tekan **F** untuk skrin penuh.
3. Gunakan **← →**, **Space** atau **klik pembentang** (*presenter clicker*). Slaid pertama ialah tajuk anugerah, diikuti setiap penerima dengan animasi nama dan konfeti.
4. Jika *"Tanda Diterima bila seterusnya"* ditanda, setiap penerima ditanda **Diterima** secara automatik apabila anda ke slaid seterusnya.

**Juru acara / urus setia**: di **Dashboard**, gunakan butang **Seterusnya ▶** untuk menggerakkan penanda *Sedang Berlangsung*. Semua telefon akan dikemas kini dalam masa ~25 saat.

**Selepas majlis**: tekan **Seterusnya ▶** sehingga *"Majlis telah selesai"*, kemudian buka **Tetapan → Laporan**. Laporan dijana automatik (skor kejayaan, jadual anugerah, kekuatan, kelemahan, cadangan, gambar lampiran). Klik **Cetak / Simpan PDF** atau **Muat turun Word** untuk menyunting.

**Ibu bapa / tetamu**: kongsi pautan `https://altrabird.github.io/Sri-Bitara-2026/` (boleh dijadikan kod QR).

---

## Sasaran anugerah & foto AJK

- **Sasaran penerima:** **Tetapan → Anugerah**, isi lajur *Sasaran* (cth. 12). Biarkan kosong untuk tiada had. Kad anugerah memaparkan `penerima / sasaran` dan bar kemajuan.
- **Foto AJK:** buat satu folder Google Drive, masukkan foto guru dan namakan setiap fail mengikut nama guru (cth. `Harsidi Bin Junick.jpg`, tanpa Pn/En/Cik). Kongsi folder: **Sesiapa yang ada pautan → Pelihat**. Tampal pautan folder di **Tetapan → AJK → Folder foto AJK**. Foto baharu muncul dalam masa ~5 minit. Guru tanpa foto dipaparkan dengan inisial (cth. HJ).

## Nota

- **Satu PIN untuk semua admin.** Kongsikan PIN hanya kepada AJK yang perlu (Slaid, Jurugambar, Urus Setia). Mod admin tamat apabila tab pelayar ditutup.
- 10 cubaan PIN salah akan mengunci log masuk selama 10 minit.
- **Tukar PIN:** edit `ADMIN_PIN` dalam Apps Script, kemudian **Deploy → Manage deployments → Edit → Version: New version → Deploy**. URL kekal sama.
- **Ubah Code.gs:** setiap perubahan mesti di-*deploy* sebagai **New version** (langkah di atas).
- Aplikasi memerlukan internet. Jika talian terputus, paparan terakhir kekal dan status bertukar kepada *"Luar talian"*.

## Ujian (pembangun)

```bash
node tests/test-backend.js
python tests/e2e.py "RUJUKAN/ANUGERAH MAJLIS APRESIASI MURID 2025.xlsx"
```
