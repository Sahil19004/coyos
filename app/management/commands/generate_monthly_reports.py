# management/commands/generate_monthly_reports.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum
from datetime import datetime, timedelta
from decimal import Decimal
from ...models import Hotel, Booking, ExtraIncome, DailyExpense, MonthlyReport
from ...utils import generate_monthly_report

class Command(BaseCommand):
    help = 'Generate monthly reports for all hotels'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regenerate reports even if they already exist',
        )
        parser.add_argument(
            '--hotel-id',
            type=int,
            help='Generate report for specific hotel ID only',
        )
        parser.add_argument(
            '--month',
            type=str,
            help='Generate report for specific month (YYYY-MM format)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting monthly report generation...')
        
        # Get all hotels or specific hotel
        if options['hotel_id']:
            try:
                hotels = [Hotel.objects.get(id=options['hotel_id'])]
                self.stdout.write(f'Generating report for hotel ID: {options["hotel_id"]}')
            except Hotel.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Hotel with ID {options["hotel_id"]} not found')
                )
                return
        else:
            hotels = Hotel.objects.all()
            self.stdout.write(f'Generating reports for {hotels.count()} hotels')
        
        generated_count = 0
        skipped_count = 0
        
        for hotel in hotels:
            try:
                if options['month']:
                    # Generate for specific month
                    month_date = datetime.strptime(options['month'], '%Y-%m').date()
                    report = self.generate_specific_month_report(hotel, month_date, options['force'])
                else:
                    # Generate for previous month
                    report = generate_monthly_report(hotel)
                
                if report:
                    generated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Generated report for {hotel.hotel_name}')
                    )
                else:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'- Skipped {hotel.hotel_name} (already exists)')
                    )
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error generating report for {hotel.hotel_name}: {str(e)}')
                )
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write(f'Generated: {generated_count} reports')
        self.stdout.write(f'Skipped: {skipped_count} reports')
        self.stdout.write('Monthly report generation completed!')
    
    def generate_specific_month_report(self, hotel, month_date, force=False):
        """Generate report for a specific month"""
        first_day = month_date.replace(day=1)
        next_month = first_day.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        
        # Check if report already exists
        if not force and MonthlyReport.objects.filter(hotel=hotel, month=first_day).exists():
            return None  # Report already generated
        
        # Delete existing report if force is True
        if force:
            MonthlyReport.objects.filter(hotel=hotel, month=first_day).delete()
        
        # Get all bookings from specified month
        bookings = Booking.objects.filter(
            hotel=hotel,
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        )
        
        # Get extra income from specified month
        extra_income = ExtraIncome.objects.filter(
            hotel=hotel,
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Get expenses from specified month
        expenses = DailyExpense.objects.filter(
            hotel=hotel,
            created_at__date__gte=first_day,
            created_at__date__lte=last_day
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Calculate QR amounts
        qr_bookings = bookings.filter(booking_mode='OYO', not_in_qr=False)
        total_qr_amount = qr_bookings.aggregate(total=Sum('return_qr'))['total'] or Decimal('0.00')
        total_booking_amount = qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
        due_to_oyo = total_booking_amount - total_qr_amount
        
        # Booking mode breakdown
        oyo_bookings = bookings.filter(booking_mode='OYO').count()
        ota_bookings = bookings.filter(booking_mode='OTA').count()
        walk_in_bookings = bookings.filter(booking_mode='WALK_IN').count()
        
        # Payment mode breakdown
        cash_payments = bookings.filter(payment_mode='CASH').count()
        upi_payments = bookings.filter(payment_mode='UPI').count()
        prepaid_payments = bookings.filter(payment_mode='PREPAID').count()
        
        # Calculate totals
        total_revenue = bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
        total_revenue += extra_income
        net_profit = total_revenue - expenses
        
        # Create monthly report
        report = MonthlyReport.objects.create(
            hotel=hotel,
            month=first_day,
            total_bookings=bookings.count(),
            total_revenue=total_revenue,
            total_oyo_due=due_to_oyo,
            total_cash_collected=bookings.filter(payment_mode='CASH').aggregate(
                total=Sum('booking_amount'))['total'] or Decimal('0.00'),
            total_qr_returned=total_qr_amount,
            total_extra_income=extra_income,
            total_expenses=expenses,
            net_profit=net_profit,
            oyo_bookings=oyo_bookings,
            ota_bookings=ota_bookings,
            walk_in_bookings=walk_in_bookings,
            cash_payments=cash_payments,
            upi_payments=upi_payments,
            prepaid_payments=prepaid_payments
        )
        
        return report