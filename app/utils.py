# utils.py
from django.utils import timezone
from django.db.models import Sum
from datetime import datetime, timedelta
from decimal import Decimal
from .models import MonthlyReport, Booking, ExtraIncome, DailyExpense
from app import models

def generate_monthly_report(hotel):
    """Generate monthly report for the previous month"""
    today = timezone.now().date()
    first_day_current_month = today.replace(day=1)
    last_day_previous_month = first_day_current_month - timedelta(days=1)
    first_day_previous_month = last_day_previous_month.replace(day=1)
    
    # Check if report already exists
    if MonthlyReport.objects.filter(hotel=hotel, month=first_day_previous_month).exists():
        return None  # Report already generated
    
    # Get all bookings from previous month
    bookings = Booking.objects.filter(
        hotel=hotel,
        created_at__date__gte=first_day_previous_month,
        created_at__date__lte=last_day_previous_month
    )
    
    # Get extra income from previous month
    extra_income = ExtraIncome.objects.filter(
        hotel=hotel,
        created_at__date__gte=first_day_previous_month,
        created_at__date__lte=last_day_previous_month
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Get expenses from previous month
    expenses = DailyExpense.objects.filter(
        hotel=hotel,
        created_at__date__gte=first_day_previous_month,
        created_at__date__lte=last_day_previous_month
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
        month=first_day_previous_month,
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

def check_and_generate_reports():
    """Check if it's time to generate monthly reports and generate them"""
    today = timezone.now().date()
    
    # Run on the 1st of each month
    if today.day == 1:
        # Get all hotels
        from .models import Hotel
        hotels = Hotel.objects.all()
        
        reports_generated = 0
        for hotel in hotels:
            report = generate_monthly_report(hotel)
            if report:
                reports_generated += 1
        
        return reports_generated
    return 0

def calculate_revenue_change(hotel, current_month_start):
    """Calculate revenue change compared to previous month"""
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    
    # Get current month revenue
    current_revenue = Booking.objects.filter(
        hotel=hotel,
        created_at__date__gte=current_month_start
    ).aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    
    # Get previous month revenue
    previous_revenue = Booking.objects.filter(
        hotel=hotel,
        created_at__date__gte=previous_month_start,
        created_at__date__lte=previous_month_end
    ).aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    
    if previous_revenue > 0:
        change = ((current_revenue - previous_revenue) / previous_revenue) * 100
        return round(float(change), 1)
    return 0

def get_dashboard_stats(hotel):
    """Get all dashboard statistics for a hotel"""
    today = timezone.now().date()
    current_month = today.month
    current_year = today.year
    
    # Calculate date ranges
    month_start = today.replace(day=1)
    next_month = month_start.replace(day=28) + timedelta(days=4)
    month_end = next_month - timedelta(days=next_month.day)
    
    # Calculate today's stats
    today_bookings = Booking.objects.filter(
        hotel=hotel, 
        created_at__date=today
    )
    
    # Calculate monthly stats
    monthly_bookings = Booking.objects.filter(
        hotel=hotel, 
        created_at__date__gte=month_start,
        created_at__date__lte=month_end
    )
    
    # QR Analysis
    qr_bookings = Booking.objects.filter(
        hotel=hotel,
        booking_mode='OYO',
        not_in_qr=False
    ).filter(
        created_at__date__gte=month_start,
        created_at__date__lte=month_end
    )
    
    total_qr_amount = qr_bookings.aggregate(total=Sum('return_qr'))['total'] or Decimal('0.00')
    total_booking_amount = qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    due_to_oyo = total_booking_amount - total_qr_amount
    
    # Extra income for current month
    extra_income = ExtraIncome.objects.filter(
        hotel=hotel,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Expenses for current month
    expenses = DailyExpense.objects.filter(
        hotel=hotel,
        created_at__date__gte=month_start,
        created_at__date__lte=month_end
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Calculate net profit
    total_revenue = (monthly_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')) + extra_income
    net_profit = total_revenue - expenses
    
    # Calculate OYO percentage
    oyo_count = monthly_bookings.filter(booking_mode='OYO').count()
    oyo_percentage = (oyo_count / monthly_bookings.count() * 100) if monthly_bookings.count() > 0 else 0
    
    return {
        'today': {
            'bookings': today_bookings.count(),
            'revenue': today_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
            'cash': today_bookings.filter(payment_mode='CASH').aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
        },
        'month': {
            'total_bookings': monthly_bookings.count(),
            'total_revenue': total_revenue,
            'total_expenses': expenses,
            'net_profit': net_profit
        },
        'qr_stats': {
            'total_qr_amount': total_qr_amount,
            'total_booking_amount': total_booking_amount,
            'due_to_oyo': due_to_oyo,
            'qr_bookings_count': qr_bookings.count()
        },
        'revenue_change': calculate_revenue_change(hotel, month_start),
        'oyo_percentage': round(oyo_percentage, 1),
        'pending_qr': qr_bookings.filter(return_qr__lt=models.F('booking_amount')).count(),
    }