# Build Installer — Client Windows

Panduan ini dijalankan di komputer **Windows** (PyInstaller build hasil
native ke OS tempat build dijalankan — build di Linux tidak menghasilkan
.exe yang jalan di Windows).

## 1. Siapkan environment build

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Build jadi single executable dengan PyInstaller

```powershell
pyinstaller --name AbsensiKiosk `
  --onefile `
  --windowed `
  --icon resources/icon.ico `
  --add-data "app/database/schema.sql;app/database" `
  main.py
```

Catatan tiap opsi:
- `--onefile` — satu file .exe, lebih mudah didistribusikan (trade-off: startup sedikit lebih lambat karena unpack ke temp folder tiap start)
- `--windowed` — tidak buka jendela terminal hitam di belakang (aplikasi kiosk, bukan tool command-line)
- `--add-data` — **wajib**, `schema.sql` dibaca saat runtime (lihat `app/database/db.py`), kalau tidak diikutkan aplikasi akan crash saat pertama kali buka database

Hasil ada di `dist/AbsensiKiosk.exe`.

### Test hasil build dulu sebelum bikin installer

```powershell
cd dist
copy ..\.env.example .env
notepad .env   # isi dengan kredensial device test
AbsensiKiosk.exe
```

## 3. Bikin installer dengan Inno Setup

Download & install [Inno Setup](https://jrsoftware.org/isinfo.php) (gratis).

Buat file `installer.iss`:

```ini
[Setup]
AppName=Absensi Kiosk SMK
AppVersion=1.0
DefaultDirName={autopf}\AbsensiKiosk
DefaultGroupName=Absensi Kiosk
OutputBaseFilename=AbsensiKiosk-Setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\AbsensiKiosk.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; DestName: ".env"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\Absensi Kiosk"; Filename: "{app}\AbsensiKiosk.exe"
Name: "{userstartup}\Absensi Kiosk"; Filename: "{app}\AbsensiKiosk.exe"

[Run]
Filename: "notepad.exe"; Parameters: "{app}\.env"; Description: "Edit konfigurasi device sebelum pertama kali jalan"; Flags: postinstall
```

Compile dengan Inno Setup Compiler (buka file `.iss`, tekan Compile,
F9) → hasil `Output\AbsensiKiosk-Setup.exe`.

**Baris `[Icons] userstartup`** otomatis membuat aplikasi jalan saat
Windows startup — tidak perlu setup manual lagi seperti di `docs/SETUP.md` langkah 6.

## 4. Distribusi ke device

1. Copy `AbsensiKiosk-Setup.exe` ke tiap komputer kiosk (USB/network share)
2. Jalankan installer — otomatis buka Notepad untuk edit `.env` di akhir instalasi
3. Isi kredensial device (lihat `docs/SETUP.md` langkah 1-2b untuk cara mendapatkannya)
4. Jalankan aplikasi dari Start Menu atau tunggu restart berikutnya (auto-start aktif)

## 5. Update versi di kemudian hari

Untuk update aplikasi tanpa install ulang dari nol:
1. Build ulang `.exe` dengan langkah 1-2
2. Ganti file `dist/AbsensiKiosk.exe` yang lama di tiap device (folder instalasi, `.env` tidak perlu diganti — tetap terpisah dari executable)

Pertimbangkan sistem auto-update di masa depan (misal cek versi ke
server saat startup) kalau jumlah device sudah banyak — untuk beberapa
device awal, update manual masih cukup praktis.
