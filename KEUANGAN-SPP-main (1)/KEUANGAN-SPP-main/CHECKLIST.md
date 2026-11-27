# Pemetaan tugas Minggu 11

| Permintaan PDF | Implementasi |
| --- | --- |
| Payment schema + 4 status | `app/models/billing.py`, `payment.py`, `payment_method.py` |
| Generate semester untuk mahasiswa aktif | `BillingService.generate_billing_for_semester`, APScheduler |
| Tarif prodi, jatuh tempo +14 hari | `semester.start_date + timedelta(days=14)` |
| Manual/webhook, transaction atomic | `PaymentService.process_payment` |
| Calculate denda, paid termasuk denda | Model Billing, job penalty, PaymentService |
| Blokir KRS | `POST /api/krs/register` menolak HTTP 403 jika ada tunggakan |
| Ringkasan mahasiswa/prodi | Dashboard utama, API billing/student, report |
| Grafik pembayaran bulanan | SVG 12 bulan terakhir, data database |
| Verifikasi signature | HMAC-SHA256 JSON canonical, constant-time compare |
| Webhook curl | `scripts/simulate_gateway.py --curl` |
| Receipt email | Notification outbox, file simulation/SMTP |
| Reminder otomatis | Job harian + deduplikasi per tagihan/hari |
| Financial report JSON | Revenue bulan berjalan, rate, top 10 per mahasiswa, rekomendasi >60 hari |
| Input CSV | Upload multipart, validasi format, analisis tanpa mengubah transaksi |
| Dashboard real-time | Polling 15 detik + refresh setelah aksi |
| Verifikasi | 24 tes unit/integrasi; SMTP menggunakan mock |

Pengiriman email ke server sungguhan membutuhkan konfigurasi SMTP milik pengguna. Insight memakai aturan deterministik; tidak mengklaim menjalankan model AI eksternal. Tidak ada gateway uang sungguhan pada proyek ini, sesuai kebutuhan simulasi PDF.
