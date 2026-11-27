# Modul Keuangan SPP — Minggu 11

Aplikasi Flask + SQLite untuk tugas manajemen pembayaran SPP. Fitur utama mengacu pada PDF tugas yang disertakan: billing semester, pembayaran/cicilan, denda, reminder, webhook simulasi, dashboard, KRS, dan laporan JSON.

## Menjalankan di Windows

1. Ekstrak ZIP, lalu buka folder `KEUANGAN-SPP-main`.
2. Pastikan Python 3.10 atau lebih baru terpasang, termasuk opsi **Add Python to PATH**.
3. Klik dua kali `RUN.bat`. Instalasi pertama membutuhkan internet.
4. Buka **http://127.0.0.1:5000**.
5. Klik **Isi data demo** untuk membuat 4 mahasiswa aktif, semester, serta tagihannya. Tombol ini tidak menimpa data mahasiswa yang sudah ada.

Alternatif terminal (Windows/Linux/macOS):

```sh
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Database dibuat otomatis pada `instance/spp_management.db`. ZIP tidak menyertakan database/transaksi/log lama. Untuk meneruskan database versi lama, ekspor/cadangkan dulu dan lakukan migrasi constraint; paket ini ditujukan untuk instalasi bersih. Jangan menimpa database kerja tanpa cadangan.

## Alur demo

1. Isi data demo. Tarif Teknik Informatika Rp5.000.000 dan Ekonomi Rp4.000.000.
2. Pada **Catat pembayaran**, pilih tagihan dan isi Rp1.000.000 untuk mencoba cicilan. Pilih manual atau simulasi webhook bertanda tangan.
3. Tagihan menjadi `partial` jika belum jatuh tempo; email bukti pembayaran muncul pada bagian **Email & reminder**.
4. Coba ajukan KRS. Sistem menolak selama ada saldo tagihan/denda yang belum dilunasi.
5. Lunasi sisanya dan ajukan kembali KRS. Data KRS tersimpan, pengajuan kedua pada semester sama ditolak.
6. Buat semester dengan tanggal awal lebih dari 14 hari yang lalu, generate tagihan, lalu klik **Jalankan billing, denda & reminder** untuk mencoba keterlambatan.
7. Periksa grafik, ringkasan per mahasiswa/prodi, top 10 tunggakan, serta unduh laporan JSON.

## Aturan pembayaran

- Tabel `billings`, `payments`, `payment_methods`; status billing `unpaid`, `partial`, `paid`, `overdue`.
- Tagihan hanya untuk mahasiswa berstatus aktif; nominal memakai tarif prodi di database. Jatuh tempo = tanggal mulai semester + 14 hari.
- Satu tagihan per mahasiswa per semester. Pemanggilan generator berulang tidak membuat tagihan ganda.
- Denda Rp10.000 per hari keterlambatan penuh, maksimum Rp500.000. Denda ikut menentukan sisa dan status pelunasan, tidak dibebankan kembali pada tagihan lunas.
- Pembayaran harus nominal Rupiah bulat positif. Kelebihan bayar ditolak dengan pesan jelas agar saldo tagihan tidak negatif.
- `partial` berlaku sebelum jatuh tempo; tagihan dengan sisa setelah jatuh tempo berstatus `overdue`.
- Record pembayaran, pembaruan tagihan, rekonsiliasi webhook dan antrean bukti pembayaran disimpan dalam satu transaksi database.
- `transaction_id` unik. Pengiriman ulang data transaksi sama menghasilkan sukses tanpa pembayaran ganda; data berbeda dengan ID yang sama ditolak.
- Update saldo memakai pemeriksaan nilai sebelumnya untuk mendeteksi perubahan bersamaan.

## Scheduler

APScheduler aktif selama satu proses aplikasi berjalan; matikan reloader agar job tidak dijalankan ganda.

| Job | Jadwal Asia/Jakarta |
| --- | --- |
| Generate billing | Saat startup lalu setiap jam, untuk semester aktif yang tanggalnya sedang berjalan |
| Update denda/status | Setiap hari pukul 00.05 |
| Reminder | Setiap hari pukul 09.00, jatuh tempo dalam 7 hari atau sudah lewat |
| Coba ulang email gagal | Setiap 5 menit |

Generator memeriksa mahasiswa baru juga. Reminder dibatasi satu per tagihan per tanggal UTC. Tanggal semester disimpan sebagai datetime UTC tanpa zona waktu. Untuk pengujian, tombol job menjalankan fungsi yang sama secara langsung. Scheduler dimatikan dalam mode pengujian; satu tes secara khusus menjalankan job tanpa konteks request.

## Email simulasi dan SMTP

Mode awal `MAIL_BACKEND=file`: pesan `.eml` disimpan di `instance/outbox` dan ditampilkan di dashboard dengan status `simulated`. Ini merupakan simulasi email, belum mengirim ke alamat asli.

Untuk mengirim email sungguhan, salin `.env.example` menjadi `.env`, lalu isi:

```ini
MAIL_BACKEND=smtp
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=alamat-pengirim@example.com
MAIL_PASSWORD=password-smtp-atau-app-password
MAIL_DEFAULT_SENDER=alamat-pengirim@example.com
```

Restart aplikasi setelah perubahan. Gunakan kredensial SMTP valid dan alamat mahasiswa asli. Status `sent` berarti server SMTP menerima pesan, bukan jaminan pesan masuk inbox. Pengiriman gagal tersimpan sebagai `failed` dan dicoba ulang. Pembayaran yang sudah sukses tidak dibatalkan hanya karena SMTP gagal. SMTP diuji menggunakan mock, belum diuji terhadap akun email sungguhan.

Antrean email bersifat at-least-once: saat proses berhenti tepat setelah SMTP menerima pesan tetapi sebelum status database tersimpan, pengiriman ulang dapat terjadi.

## Webhook dengan curl

Jalankan aplikasi, buat data demo, kemudian jalankan:

```sh
python scripts/simulate_gateway.py --billing-id 1 --amount 1000000 --method-id 1 --transaction-id TEST-CURL-001 --curl
```

Script membuat `webhook_payload.json` dengan signature HMAC-SHA256 dan memanggil curl. Alternatif kirim manual:

```sh
curl -X POST http://127.0.0.1:5000/api/webhook/payment -H "Content-Type: application/json" --data-binary @webhook_payload.json
```

Kirim file yang sama dua kali untuk membuktikan idempotensi. Ubah nominal tanpa menghitung ulang signature untuk membuktikan penolakan HTTP 401. Gunakan ID tagihan/metode yang tersedia. HTTP 200 untuk webhook sukses/duplikat/pending/failed; pending dan failed tidak menambah pembayaran. Signature memakai JSON canonical: semua field selain `signature`, key diurutkan, separator `,` dan `:`, UTF-8. Script dan server memakai format identik.

## Dashboard dan laporan

- Halaman utama responsif dengan pembaruan otomatis setiap 15 detik dan setelah aksi.
- Ringkasan tagihan mahasiswa, pembayaran, sisa termasuk denda; grafik pembayaran 12 bulan terakhir.
- Collection rate prodi berdasarkan nominal; kartu **Mahasiswa lunas** berdasarkan jumlah mahasiswa bertagihan yang telah melunasi semua tagihannya.
- Pendapatan laporan utama memakai bulan kalender berjalan sampai sekarang.
- Tunggakan terbesar dijumlahkan per mahasiswa, bukan per baris billing; total outstanding menghitung semua tagihan.
- Rekomendasi khusus mahasiswa dengan tunggakan lebih dari 60 hari (pendekatan dua bulan).
- Insight dibuat dengan aturan analisis deterministik (`method=rule_based`), bukan panggilan model AI eksternal. Tidak membutuhkan API key.

CSV diunggah melalui panel **Analisis CSV** atau `POST /api/reports/finance/csv` (multipart, field `file`, maksimum 2 MB). Kolom wajib `nim,jumlah,tanggal,status`; gunakan UTF-8, nominal tanpa pemisah ribuan, tanggal ISO tanpa zona waktu. Lihat `examples/payment_data.csv`. Status sukses `paid`, `confirmed`, `success`; status lainnya tidak dihitung sebagai revenue. CSV bersifat analisis, tidak menulis transaksi ke database. Revenue/grafik CSV memakai baris sukses dalam periode bulan berjalan; saldo tagihan, collection rate dan top tunggakan tetap mengambil database karena kolom CSV tidak memuat nilai kewajiban tagihan.

## Endpoint utama

| Method | URL | Fungsi |
| --- | --- | --- |
| GET | `/` atau `/dashboard` | Dashboard lengkap |
| POST | `/api/demo/init` | Isi demo, development/testing |
| GET/POST | `/api/student` | Daftar/tambah mahasiswa |
| GET | `/api/programs` | Daftar prodi dan tarif |
| POST | `/api/semesters` | Buat semester aktif |
| GET | `/api/billing/semesters` | Daftar semester |
| POST | `/api/billing/generate/<semester_id>` | Generate tagihan |
| GET | `/api/billing/student/<student_id>` | Ringkasan dan tagihan mahasiswa |
| POST | `/api/payment/process` | Pembayaran manual |
| GET | `/api/payment/methods` | Metode aktif |
| POST | `/api/webhook/payment` | Webhook bertanda tangan |
| POST | `/api/webhook/simulate-payment` | Simulasi, development/testing |
| POST | `/api/krs/register` | Simpan KRS dengan blokir tunggakan |
| GET | `/api/reports/finance` | Laporan JSON lengkap |
| POST | `/api/reports/finance/csv` | Analisis CSV |
| GET | `/api/notifications` | Status dan isi email |
| POST | `/api/jobs/run` | Jalankan job untuk demo |

Aplikasi merupakan demonstrasi tugas lokal tanpa autentikasi. Jalankan satu proses scheduler. Pendaftaran KRS adalah simulasi penyimpanan daftar kode MK pada modul ini; jika digabung ke aplikasi akademik lain, gunakan pemeriksaan tunggakan yang sama pada endpoint KRS aplikasi tersebut.

## Pengujian

```sh
python -m unittest discover -s tests -v
```

24 tes unit/integrasi mencakup generator dan jatuh tempo, job tanpa request context, semester masa depan, webhook/signature/replay, status pending/failed, cicilan/pelunasan/denda, nominal invalid/kelebihan bayar, konflik ID transaksi, rollback atomik, pemblokiran/pendaftaran KRS, reminder, email gagal dan retry SMTP mock, laporan agregat, CSV, serta endpoint dashboard. Lihat `TEST_RESULTS.txt`.

Dokumen lama disimpan pada `docs/legacy` sebagai referensi versi awal; panduan versi lengkap ini adalah README ini dan `CHECKLIST.md`.
