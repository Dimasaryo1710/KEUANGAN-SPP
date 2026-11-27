from collections import defaultdict
from datetime import datetime
import csv
import io
import json
from app.models.student import Student, ProgramStudi
from app.models.billing import Billing
from app.models.payment import Payment

class AIFinancialService:
    """Analisis keuangan berbasis aturan, tanpa ketergantungan API AI eksternal."""
    def __init__(self, app=None): self.app = app

    def generate_financial_report(self, start_date=None, end_date=None, csv_text=None):
        now = end_date or datetime.utcnow()
        start = start_date or now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start > now: raise ValueError('Tanggal mulai melebihi tanggal akhir')
        students = Student.query.all()
        bills = Billing.query.all()
        payments = Payment.query.filter(Payment.status == 'confirmed', Payment.confirmation_date >= start, Payment.confirmation_date <= now).all()
        transactions = [dict(nim=row.student.nim, amount=row.amount, date=row.confirmation_date) for row in payments]
        if csv_text is not None:
            reader = csv.DictReader(io.StringIO(csv_text.lstrip('\ufeff')))
            if not {'nim', 'jumlah', 'tanggal', 'status'}.issubset(reader.fieldnames or []):
                raise ValueError('Kolom CSV wajib: nim,jumlah,tanggal,status')
            transactions = []
            for index, row in enumerate(reader, 2):
                try:
                    amount = int(row['jumlah'])
                    date = datetime.fromisoformat(row['tanggal'])
                    if date.tzinfo is not None: raise ValueError('Gunakan tanggal tanpa zona waktu')
                    if amount <= 0 or not row['nim'].strip(): raise ValueError('Data pembayaran tidak valid')
                    status = row['status'].strip().lower()
                    if status not in ['confirmed', 'success', 'paid', 'pending', 'failed', 'unpaid', 'partial', 'overdue']:
                        raise ValueError('Status tidak dikenali')
                    if start <= date <= now and status in ['confirmed', 'success', 'paid']:
                        transactions.append(dict(nim=row['nim'], amount=amount, date=date))
                except (ValueError, TypeError) as exc:
                    raise ValueError(f'CSV baris {index}: {exc}') from exc
        outstanding = defaultdict(int)
        late = set()
        over_two_months = set()
        for bill in bills:
            outstanding[bill.student_id] += max(0, bill.remaining_amount)
            if bill.remaining_amount > 0 and bill.due_date < now:
                late.add(bill.student_id)
                if (now-bill.due_date).days > 60: over_two_months.add(bill.student_id)
        total_billed = sum(b.total_amount + b.penalty for b in bills)
        total_paid = sum(b.paid_amount for b in bills)
        billed_ids = {b.student_id for b in bills}
        fully_paid = {sid for sid in billed_ids if outstanding[sid] == 0}
        rate = len(fully_paid)/len(billed_ids)*100 if billed_ids else 0
        profiles = {s.id:s for s in students}
        top = sorted([(sid, amount) for sid, amount in outstanding.items() if amount > 0], key=lambda item: (-item[1], item[0]))[:10]
        historical = Payment.query.filter(Payment.status == 'confirmed').all() if csv_text is None else []
        monthly = []
        for offset in range(11, -1, -1):
            month_index = now.year*12 + now.month-1-offset
            year, month0 = divmod(month_index, 12)
            month = month0+1
            if csv_text is None:
                values = historical
                amount = sum(v.amount for v in values if v.confirmation_date and v.confirmation_date.year == year and v.confirmation_date.month == month and v.confirmation_date <= now)
            else:
                amount = sum(v['amount'] for v in transactions if v['date'].year == year and v['date'].month == month)
            monthly.append(dict(month=f'{year}-{month:02}', amount=amount))
        programs = []
        for program in ProgramStudi.query.all():
            ids = {s.id for s in students if s.program_studi_id == program.id} & billed_ids
            own = [b for b in bills if b.student_id in ids]
            billed = sum(b.total_amount + b.penalty for b in own)
            paid = sum(b.paid_amount for b in own)
            programs.append(dict(program_studi=program.name, num_students=len(ids), total_billed=billed, total_paid=paid, collection_rate=round(paid/billed*100,2) if billed else 0))
        return dict(period=dict(start_date=start.isoformat(), end_date=now.isoformat()), source='csv' if csv_text is not None else 'database', revenue_metrics=dict(total_revenue=sum(t['amount'] for t in transactions), total_payments=len(transactions), total_billed=total_billed, total_paid=total_paid, collection_rate=round(rate,2), amount_collection_rate=round(total_paid/total_billed*100,2) if total_billed else 0), outstanding=dict(total_outstanding=sum(outstanding.values()), num_overdue_students=len(late), total_overdue=sum(b.remaining_amount for b in bills if b.remaining_amount > 0 and b.due_date < now), students_over_two_months=len(over_two_months)), top_outstanding_billings=[dict(student_nim=profiles[sid].nim, student_name=profiles[sid].name, amount=amount) for sid, amount in top], monthly_payments=monthly, program_studi_statistics=programs, ai_insights=dict(method='rule_based', insights=[f'{len(fully_paid)} dari {len(billed_ids)} mahasiswa bertagihan sudah lunas.', f'{len(late)} mahasiswa memiliki tunggakan jatuh tempo.'], recommendations=[f'Kirim reminder ke {len(over_two_months)} mahasiswa dengan tunggakan lebih dari 2 bulan.', 'Prioritaskan 10 mahasiswa dengan tunggakan terbesar.'], generated_at=datetime.utcnow().isoformat()), notes='Revenue CSV dihitung dari transaksi sukses dalam periode; saldo tagihan dan collection rate memakai database. CSV tidak mengubah database.' if csv_text is not None else 'Collection rate: persentase mahasiswa bertagihan yang lunas; amount_collection_rate: persentase nominal terbayar.')

    def get_student_financial_profile(self, student_id):
        student = Student.query.get(student_id)
        if not student: return {'error':'Mahasiswa tidak ditemukan'}
        bills = Billing.query.filter_by(student_id=student_id).all()
        total = sum(b.total_amount+b.penalty for b in bills)
        paid = sum(b.paid_amount for b in bills)
        return dict(student=dict(nim=student.nim,name=student.name,email=student.email,program_studi=student.program_studi.name), financial_summary=dict(total_billed=total,total_paid=paid,total_outstanding=sum(b.remaining_amount for b in bills),payment_percentage=paid/total*100 if total else 0),billing_details=[dict(id=b.id,semester=b.semester,total=b.total_amount+b.penalty,paid=b.paid_amount,remaining=b.remaining_amount,status=b.status,due_date=b.due_date.isoformat()) for b in bills])

    def export_report_to_json(self, report): return json.dumps(report, indent=2)
