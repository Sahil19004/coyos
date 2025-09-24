from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum, Count, Q,F
from .utils import generate_monthly_report, check_and_generate_reports
from django.utils import timezone
from django.core.paginator import Paginator
from datetime import datetime, timedelta
import json
from decimal import Decimal
from datetime import datetime, timedelta
from .models import *
from decimal import Decimal
from .forms import *
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from datetime import date

from .models import *

def login_view(request):
    """Login page view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Check if user has a hotel associated
            try:
                hotel = Hotel.objects.get(user=user)
                if hotel.is_active:
                    login(request, user)
                    messages.success(request, f'Welcome back, {hotel.hotel_name}!')
                    return redirect('dashboard')
                else:
                    messages.error(request, 'Your hotel account is inactive. Please contact support.')
            except Hotel.DoesNotExist:
                messages.error(request, 'No hotel associated with this account.')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')

def logout_view(request):
    """Logout view"""
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('login')

@login_required
def dashboard(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
    except Hotel.DoesNotExist:
        return redirect('login')
    
    # Check if we need to generate monthly reports
    check_and_generate_reports()
    
    # Get current date and time
    today = timezone.now().date()
    
    # Handle date filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Set default date range (current month if no dates provided)
    if not start_date:
        month_start = today.replace(day=1)
        start_date = month_start
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        next_month = today.replace(day=28) + timedelta(days=4)
        month_end = next_month - timedelta(days=next_month.day)
        end_date = min(month_end, today)  # Don't exceed today's date
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        if end_date > today:
            end_date = today
    
    # Ensure start_date is not after end_date
    if start_date > end_date:
        start_date = end_date
    
    # Calculate today's stats (always current day, not filtered)
    today_bookings = Booking.objects.filter(
        hotel=hotel, 
        created_at__date=today
    )
    
    # Calculate filtered stats based on date range
    filtered_bookings = Booking.objects.filter(
        hotel=hotel, 
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    
    # QR Analysis for filtered period
    qr_bookings = Booking.objects.filter(
        hotel=hotel,
        booking_mode='OYO',
        not_in_qr=False
    ).filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    
    total_qr_amount = qr_bookings.aggregate(total=Sum('return_qr'))['total'] or Decimal('0.00')
    total_booking_amount = qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    due_to_oyo = total_booking_amount - total_qr_amount
    
    # Extra income for filtered period
    extra_income = ExtraIncome.objects.filter(
        hotel=hotel,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Expenses for filtered period
    expenses = DailyExpense.objects.filter(
        hotel=hotel,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Calculate net profit for filtered period
    total_revenue = (filtered_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')) + extra_income
    net_profit = total_revenue - expenses
    
    # Get previous reports for charts (last 6 months regardless of filter)
    previous_reports = MonthlyReport.objects.filter(hotel=hotel).order_by('-month')[:6]
    
    # Prepare data for charts - monthly data (unchanged)
    months_data = []
    for report in reversed(previous_reports):  # Show oldest first in chart
        months_data.append({
            'month': report.month.strftime('%b %Y'),
            'revenue': float(report.total_revenue),
            'expenses': float(report.total_expenses),
            'profit': float(report.net_profit)
        })
    
    # If we don't have enough historical data, fill with current month data
    if len(months_data) < 6:
        # Get current month data for filling
        current_month_start = today.replace(day=1)
        next_month = current_month_start.replace(day=28) + timedelta(days=4)
        current_month_end = next_month - timedelta(days=next_month.day)
        
        current_month_bookings = Booking.objects.filter(
            hotel=hotel, 
            created_at__date__gte=current_month_start,
            created_at__date__lte=current_month_end
        )
        
        current_extra_income = ExtraIncome.objects.filter(
            hotel=hotel,
            created_at__date__gte=current_month_start,
            created_at__date__lte=current_month_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        current_expenses = DailyExpense.objects.filter(
            hotel=hotel,
            created_at__date__gte=current_month_start,
            created_at__date__lte=current_month_end
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        current_total_revenue = (current_month_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')) + current_extra_income
        current_net_profit = current_total_revenue - current_expenses
        
        months_data.append({
            'month': current_month_start.strftime('%b %Y'),
            'revenue': float(current_total_revenue),
            'expenses': float(current_expenses),
            'profit': float(current_net_profit)
        })
    
    # Daily data for the filtered period
    daily_data = []
    date_range_days = (end_date - start_date).days + 1
    
    for i in range(date_range_days):
        current_date = start_date + timedelta(days=i)
        if current_date <= today:  # Only include dates up to today
            day_bookings = Booking.objects.filter(
                hotel=hotel,
                created_at__date=current_date
            )
            day_revenue = day_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
            daily_data.append(float(day_revenue))
    
    # Recent bookings (all time, not filtered)
    recent_bookings = Booking.objects.filter(hotel=hotel).order_by('-created_at')[:10]
    
    # Booking mode breakdown for filtered period
    booking_modes = filtered_bookings.values('booking_mode').annotate(
        count=Count('id'),
        total_revenue=Sum('booking_amount')
    )
    
    # Calculate OYO percentage for filtered period
    oyo_count = filtered_bookings.filter(booking_mode='OYO').count()
    total_bookings_count = filtered_bookings.count()
    oyo_percentage = (oyo_count / total_bookings_count * 100) if total_bookings_count > 0 else 0
    
    # Calculate revenue change compared to previous period of same duration
    previous_period_days = (end_date - start_date).days + 1
    previous_period_start = start_date - timedelta(days=previous_period_days)
    previous_period_end = start_date - timedelta(days=1)
    
    previous_period_bookings = Booking.objects.filter(
        hotel=hotel,
        created_at__date__gte=previous_period_start,
        created_at__date__lte=previous_period_end
    )
    
    previous_revenue = previous_period_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    current_revenue = filtered_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    
    if previous_revenue > 0:
        revenue_change = ((current_revenue - previous_revenue) / previous_revenue) * 100
    else:
        revenue_change = 100 if current_revenue > 0 else 0
    
    context = {
        'hotel': hotel,
        'today': today,
        'start_date': start_date,
        'end_date': end_date,
        'stats': {
            'today': {
                'bookings': today_bookings.count(),
                'revenue': today_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
                'cash': today_bookings.filter(payment_mode='CASH').aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
                'qr_due': due_to_oyo
            },
            'month': {
                'total_bookings': filtered_bookings.count(),
                'total_revenue': total_revenue,
                'total_expenses': expenses,
                'net_profit': net_profit
            },
            'revenue_change': round(revenue_change, 1),
            'oyo_percentage': round(oyo_percentage, 1),
        },
        'qr_stats': {
            'total_qr_amount': total_qr_amount,
            'total_booking_amount': total_booking_amount,
            'due_to_oyo': due_to_oyo,
            'qr_bookings_count': qr_bookings.count()
        },
        'pending_qr': qr_bookings.filter(return_qr__lt=F('booking_amount')).count(),
        'monthly_data': months_data,
        'daily_data': daily_data,
        'recent_bookings': recent_bookings,
        'booking_modes': booking_modes,
        'previous_reports': previous_reports,
    }
    
    return render(request, 'dashboard.html', context)
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
@login_required
def booking(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have a hotel associated with your account.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        # This is only for creating new bookings now
        form = BookingForm(request.POST)
            
        if form.is_valid():
            booking = form.save(commit=False)
            booking.hotel = hotel
            booking.save()
            messages.success(request, f'Booking {booking.booking_id} created successfully!')
            return redirect('booking')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingForm()
    
    # Get all bookings for this hotel
    bookings = Booking.objects.filter(hotel=hotel).order_by('-created_at')
    
    # Prepare booking data for JavaScript
    booking_data = {}
    for booking in bookings:
        booking_data[booking.id] = {
            'booking_id': booking.booking_id,
            'guest_name': booking.guest_name,
            'booking_mode': booking.booking_mode,
            'payment_mode': booking.payment_mode,
            'booking_amount': float(booking.booking_amount),
            'return_qr': float(booking.return_qr),
            'not_in_qr': booking.not_in_qr,
            'extra_income': float(booking.extra_income) if booking.extra_income else 0,
        }
   
    
    return render(request, "bookings.html", {
        'form': form,
        'bookings': bookings,
        'hotel': hotel,
        'booking_data_json': json.dumps(booking_data),
        # Add this to context
    })
@login_required
@require_POST
def update_booking(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
        
        # Get the numeric ID from the form, not the booking_id string
        booking_id = request.POST.get('id')  # Changed from 'booking_id' to 'id'
        booking_instance = get_object_or_404(Booking, id=booking_id, hotel=hotel)
        
        form = BookingForm(request.POST, instance=booking_instance)
        if form.is_valid():
            form.save()
            messages.success(request, f'Booking {booking_instance.booking_id} updated successfully!')
            return redirect('booking')
        else:
            # For debugging, print form errors
            print(form.errors)
            messages.error(request, 'Please correct the errors below.')
            return redirect('booking')
            
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to edit this booking.")
        return redirect('booking')
    except ValueError as e:
        # Handle the case where ID is not a number
        messages.error(request, "Invalid booking ID format.")
        return redirect('booking')
@login_required
def delete_booking(request, booking_id):
    try:
        hotel = Hotel.objects.get(user=request.user)
        booking = get_object_or_404(Booking, id=booking_id, hotel=hotel)
        booking_id_str = booking.booking_id
        booking.delete()
        messages.success(request, f'Booking {booking_id_str} deleted successfully!')
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to delete this booking.")
    
    return redirect('booking')



@login_required
def extra_income(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have a hotel associated with your account.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ExtraIncomeForm(request.POST, hotel=hotel)
        if form.is_valid():
            income = form.save(commit=False)
            income.hotel = hotel
            income.save()
            
            # Update booking extra income if this income is associated with a booking
            if income.booking:
                update_booking_extra_income(hotel, income.booking.id)
            
            messages.success(request, f'Extra income of ₹{income.amount} added successfully!')
            return redirect('extra_income')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ExtraIncomeForm(hotel=hotel)
    
    # Get all extra incomes for this hotel
    incomes = ExtraIncome.objects.filter(hotel=hotel).order_by('-created_at')
    
    # Calculate total extra income
    total_income = incomes.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    
    return render(request, "extra_income.html", {
        'form': form,
        'incomes': incomes,
        'hotel': hotel,
        'total_income': total_income,
    })

@login_required
@require_POST
def update_extra_income(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
        income_id = request.POST.get('id')
        income_instance = get_object_or_404(ExtraIncome, id=income_id, hotel=hotel)
        
        # Store the original booking for comparison
        original_booking = income_instance.booking
        
        # Get the operation type (add/subtract) and amount
        operation = request.POST.get('operation', 'add')
        amount_change = Decimal(request.POST.get('amount_change', 0))
        
        # Update the amount based on operation
        if operation == 'add':
            income_instance.amount += amount_change
        elif operation == 'subtract':
            income_instance.amount = max(Decimal('0.00'), income_instance.amount - amount_change)
        
        # Update other fields
        income_instance.source = request.POST.get('source')
        income_instance.description = request.POST.get('description')
        
        # Update booking if provided
        booking_id = request.POST.get('booking')
        if booking_id:
            booking = get_object_or_404(Booking, id=booking_id, hotel=hotel)
            income_instance.booking = booking
        else:
            income_instance.booking = None
        
        income_instance.save()
        
        # Update booking extra income for both old and new bookings if they changed
        if original_booking:
            update_booking_extra_income(hotel, original_booking.id)
        
        if income_instance.booking and income_instance.booking != original_booking:
            update_booking_extra_income(hotel, income_instance.booking.id)
        
        messages.success(request, f'Extra income updated successfully!')
        return redirect('extra_income')
            
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to edit this income.")
        return redirect('extra_income')
    except ValueError as e:
        messages.error(request, "Invalid amount format.")
        return redirect('extra_income')
    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('extra_income')

@login_required
def delete_extra_income(request, income_id):
    try:
        hotel = Hotel.objects.get(user=request.user)
        income = get_object_or_404(ExtraIncome, id=income_id, hotel=hotel)
        
        # Store the booking reference before deletion
        booking_id = income.booking.id if income.booking else None
        
        income.delete()
        
        # Update booking extra income if this income was associated with a booking
        if booking_id:
            update_booking_extra_income(hotel, booking_id)
        
        messages.success(request, 'Extra income deleted successfully!')
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to delete this income.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting: {str(e)}")
    
    return redirect('extra_income')

def update_booking_extra_income(hotel, booking_id):
    """Update the extra_income field for a specific booking based on all its extra incomes"""
    try:
        # Get the booking object
        booking = get_object_or_404(Booking, id=booking_id, hotel=hotel)
        
        # Calculate total extra income for this specific booking
        total_extra_income = ExtraIncome.objects.filter(
            hotel=hotel, 
            booking=booking
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        
        # Update the booking
        booking.extra_income = total_extra_income
        booking.save()
        
        print(f"Updated booking {booking_id} with extra income: {total_extra_income}")
        
    except Booking.DoesNotExist:
        print(f"Booking with ID {booking_id} not found for hotel {hotel}")
    except Exception as e:
        print(f"Error updating booking extra income: {e}")

def update_all_bookings_extra_income(hotel):
    """Update extra_income field for all bookings based on their associated extra incomes"""
    try:
        # Get all bookings for this hotel
        bookings = Booking.objects.filter(hotel=hotel)
        
        for booking in bookings:
            # Calculate total extra income for this specific booking
            total_extra_income = ExtraIncome.objects.filter(
                hotel=hotel, 
                booking=booking
            ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
            
            # Update the booking
            booking.extra_income = total_extra_income
            booking.save()
            
        print(f"Updated extra income for all bookings of hotel {hotel}")
        
    except Exception as e:
        print(f"Error updating all bookings extra income: {e}")



@login_required
def expenses(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have a hotel associated with your account.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = DailyExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.hotel = hotel
            expense.save()
            
            messages.success(request, f'Expense of ₹{expense.amount} added successfully!')
            return redirect('expenses')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = DailyExpenseForm()
    
    # Get all expenses for this hotel
    expenses = DailyExpense.objects.filter(hotel=hotel).order_by('-created_at')
    
    # Calculate total expenses by category
    expense_categories = {
        'STAFF_SALARY': {'name': 'Staff Salary / Wages', 'total': Decimal('0.00')},
        'KITCHEN_GROCERY': {'name': 'Kitchen / Grocery', 'total': Decimal('0.00')},
        'ELECTRICITY_WATER': {'name': 'Electricity / Water Bill', 'total': Decimal('0.00')},
        'MAINTENANCE': {'name': 'Maintenance', 'total': Decimal('0.00')},
        'OTHER': {'name': 'Other', 'total': Decimal('0.00')},
    }
    
    for expense in expenses:
        if expense.expense_type in expense_categories:
            expense_categories[expense.expense_type]['total'] += expense.amount
    
    # Calculate total expenses
    total_expenses = expenses.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    
    return render(request, "expense.html", {
        'form': form,
        'expenses': expenses,
        'hotel': hotel,
        'expense_categories': expense_categories,
        'total_expenses': total_expenses,
    })

@login_required
@require_POST
def update_expense(request):
    try:
        hotel = Hotel.objects.get(user=request.user)
        expense_id = request.POST.get('id')
        expense_instance = get_object_or_404(DailyExpense, id=expense_id, hotel=hotel)
        
        # Update the amount
        amount = Decimal(request.POST.get('amount', 0))
        if amount > 0:
            expense_instance.amount = amount
        
        # Update other fields
        expense_instance.expense_type = request.POST.get('expense_type')
        expense_instance.description = request.POST.get('description')
        
        expense_instance.save()
        
        messages.success(request, f'Expense updated successfully!')
        return redirect('expenses')
            
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to edit this expense.")
        return redirect('expenses')
    except ValueError as e:
        messages.error(request, "Invalid amount format.")
        return redirect('expenses')

@login_required
def delete_expense(request, expense_id):
    try:
        hotel = Hotel.objects.get(user=request.user)
        expense = get_object_or_404(DailyExpense, id=expense_id, hotel=hotel)
        expense.delete()
        messages.success(request, 'Expense deleted successfully!')
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to delete this expense.")
    
    return redirect('expenses')

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from datetime import date, datetime, timedelta
from decimal import Decimal
from .models import Hotel, SimpleBooking

def blackroom(request):
    # Get current hotel
    hotel = get_object_or_404(Hotel, id=request.user.hotel.id)
    
    # Handle date filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Set default date range (current month if no dates provided)
    if not start_date:
        today = timezone.now().date()
        month_start = today.replace(day=1)
        start_date = month_start
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = timezone.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Ensure start_date is not after end_date
    if start_date > end_date:
        start_date = end_date
    
    # Get filtered bookings
    simple_bookings = SimpleBooking.objects.filter(
        hotel=hotel,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).order_by('-created_at')
    
    # Calculate summary statistics for filtered period
    total_bookings = simple_bookings.count()
    total_amount = simple_bookings.aggregate(Sum('booking_amount'))['booking_amount__sum'] or Decimal('0.00')
    total_extra_income = simple_bookings.aggregate(Sum('extra_income'))['extra_income__sum'] or Decimal('0.00')
    
    # Calculate monthly data for charts
    monthly_data = []
    current_date = start_date.replace(day=1)
    
    while current_date <= end_date:
        month_start = current_date.replace(day=1)
        next_month = month_start.replace(day=28) + timedelta(days=4)
        month_end = next_month - timedelta(days=next_month.day)
        
        if month_end > end_date:
            month_end = end_date
        
        monthly_bookings = SimpleBooking.objects.filter(
            hotel=hotel,
            created_at__date__gte=month_start,
            created_at__date__lte=month_end
        )
        
        month_revenue = monthly_bookings.aggregate(Sum('booking_amount'))['booking_amount__sum'] or Decimal('0.00')
        month_extra_income = monthly_bookings.aggregate(Sum('extra_income'))['extra_income__sum'] or Decimal('0.00')
        month_total = month_revenue + month_extra_income
        
        monthly_data.append({
            'month': month_start.strftime('%b %Y'),
            'revenue': float(month_revenue),
            'extra_income': float(month_extra_income),
            'total': float(month_total),
            'bookings_count': monthly_bookings.count()
        })
        
        # Move to next month
        if current_date.month == 12:
            current_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            current_date = current_date.replace(month=current_date.month + 1)
    
    # Daily data for current month
    daily_data = []
    current_month_start = timezone.now().date().replace(day=1)
    next_month = current_month_start.replace(day=28) + timedelta(days=4)
    current_month_end = next_month - timedelta(days=next_month.day)
    
    for i in range(1, min(timezone.now().date().day + 1, 32)):
        day_date = timezone.now().date().replace(day=i)
        day_bookings = SimpleBooking.objects.filter(
            hotel=hotel,
            created_at__date=day_date
        )
        day_revenue = day_bookings.aggregate(Sum('booking_amount'))['booking_amount__sum'] or Decimal('0.00')
        day_extra_income = day_bookings.aggregate(Sum('extra_income'))['extra_income__sum'] or Decimal('0.00')
        daily_data.append(float(day_revenue + day_extra_income))
    
    if request.method == 'POST':
        # Handle form submission for new booking
        guest_name = request.POST.get('guest_name')
        booking_amount = request.POST.get('booking_amount')
        extra_income = request.POST.get('extra_income', '0.00')
        
        # Validate and create booking
        try:
            booking = SimpleBooking(
                hotel=hotel,
                guest_name=guest_name,
                booking_amount=Decimal(booking_amount),
                extra_income=Decimal(extra_income)
            )
            booking.save()
            messages.success(request, 'Booking added successfully!')
            return redirect('blackroom')
        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')
    
    context = {
        'bookings': simple_bookings,
        'today': timezone.now().date(),
        'hotel': hotel,
        'total_bookings': total_bookings,
        'total_amount': total_amount,
        'total_extra_income': total_extra_income,
        'start_date': start_date,
        'end_date': end_date,
        'monthly_data': monthly_data,
        'daily_data': daily_data,
        'grand_total': total_amount + total_extra_income,
    }
    return render(request, 'simplebook.html', context)

def edit_simple_booking(request, booking_id):
    booking = get_object_or_404(SimpleBooking, id=booking_id)
    
    if request.method == 'POST':
        # Handle form submission for editing
        booking.guest_name = request.POST.get('guest_name')
        booking.booking_amount = request.POST.get('booking_amount')
        booking.extra_income = request.POST.get('extra_income', '0.00')
        
        try:
            booking.save()
            messages.success(request, 'Booking updated successfully!')
            return redirect('blackroom')
        except Exception as e:
            messages.error(request, f'Error updating booking: {str(e)}')
    
    return redirect('blackroom')

def delete_simple_booking(request, booking_id):
    booking = get_object_or_404(SimpleBooking, id=booking_id)
    
    try:
        booking.delete()
        messages.success(request, 'Booking deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting booking: {str(e)}')
    
    return redirect('blackroom')