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
    
    # Set default date range (SAME DAY if no dates provided)
    if not start_date:
        start_date = today
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = today
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
        booking_date=today
    )
    
    # Today's extra income - CHANGED to use date field
    today_extra_income = ExtraIncome.objects.filter(
        hotel=hotel,
        date=today
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Today's expenses - CHANGED to use date field
    today_expenses = DailyExpense.objects.filter(
        hotel=hotel,
        date=today
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Calculate today's revenue (bookings + extra income - expenses)
    today_booking_revenue = today_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    today_revenue = today_booking_revenue + today_extra_income - today_expenses
    
    # Calculate filtered stats based on date range
    filtered_bookings = Booking.objects.filter(
        hotel=hotel, 
        booking_date__gte=start_date,
        booking_date__lte=end_date
    )
    
    # QR Analysis for ALL booking modes (OYO, TA, OTA, WALK_IN) - all part of OYO ecosystem
    oyo_ecosystem_modes = ['OYO', 'TA', 'OTA', 'WALK_IN']
    
    # Get all QR bookings for OYO ecosystem (exclude PREPAID from QR amount calculation)
    qr_bookings = Booking.objects.filter(
        hotel=hotel,
        booking_mode__in=oyo_ecosystem_modes,
        not_in_qr=False  # Only include bookings that are in QR
    ).filter(
        booking_date__gte=start_date,
        booking_date__lte=end_date
    )
    
    # Separate prepaid and non-prepaid bookings for QR calculation
    non_prepaid_qr_bookings = qr_bookings.exclude(payment_mode='PREPAID')
    prepaid_qr_bookings = qr_bookings.filter(payment_mode='PREPAID')
    
    # Calculate QR amounts - Only actual QR return amounts, not excess
    total_qr_returned = non_prepaid_qr_bookings.aggregate(total=Sum('return_qr'))['total'] or Decimal('0.00')
    
    # Calculate total QR booking amount - ONLY NON-PREPAID bookings count towards QR Amount
    total_qr_booking_amount = non_prepaid_qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    
    # Calculate due amounts separately for prepaid and non-prepaid
    non_prepaid_due = non_prepaid_qr_bookings.aggregate(
        total=Sum(F('booking_amount') - F('return_qr'))
    )['total'] or Decimal('0.00')
    
    prepaid_due = prepaid_qr_bookings.aggregate(
        total=Sum(F('booking_amount') - F('return_qr'))
    )['total'] or Decimal('0.00')
    
    # Total due from OYO ecosystem bookings (before adjusting for not_in_qr)
    total_oyo_due = non_prepaid_due + prepaid_due
    
    # Get bookings NOT in QR for OYO ecosystem
    not_in_qr_bookings = Booking.objects.filter(
        hotel=hotel,
        booking_mode__in=oyo_ecosystem_modes,
        not_in_qr=True
    ).filter(
        booking_date__gte=start_date,
        booking_date__lte=end_date
    )
    
    # Get hotel's QR amount (from Hotel model)
    hotel_qr_amount = Decimal(str(hotel.qr_amount or 0))
    
    # Calculate not_in_qr adjustments
    # For each not_in_qr booking: difference = booking_amount - hotel_qr_amount
    not_in_qr_total_booking = not_in_qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    not_in_qr_count = not_in_qr_bookings.count()
    
    # Total QR that would have been received for these bookings
    not_in_qr_expected_qr = hotel_qr_amount * not_in_qr_count
    
    # The difference (amount over the expected QR)
    not_in_qr_adjustment = not_in_qr_total_booking - not_in_qr_expected_qr
    
    # Add this adjustment to total QR returned amount (as if you received this extra)
    adjusted_qr_returned = total_qr_returned + not_in_qr_adjustment
    
    # Subtract this adjustment from due to OYO
    due_to_oyo = total_oyo_due - not_in_qr_adjustment
    
    # Track if there's excess (negative due means OYO owes you money)
    excess_amount = abs(due_to_oyo) if due_to_oyo < 0 else Decimal('0.00')
    
    # Extra income for filtered period - CHANGED to use date field
    extra_income = ExtraIncome.objects.filter(
        hotel=hotel,
        date__gte=start_date,
        date__lte=end_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Expenses for filtered period - CHANGED to use date field
    expenses = DailyExpense.objects.filter(
        hotel=hotel,
        date__gte=start_date,
        date__lte=end_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Calculate net profit for filtered period
    total_revenue = (filtered_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')) + extra_income
    net_profit = total_revenue - expenses
    
    # Calculate total rooms used in filtered period
    total_rooms_used = filtered_bookings.aggregate(total=Sum('number_of_rooms'))['total'] or 0
    
    # Recent bookings (all time, not filtered)
    recent_bookings = Booking.objects.filter(hotel=hotel).order_by('-created_at')[:10]
    
    # Booking mode breakdown for filtered period
    booking_modes = filtered_bookings.values('booking_mode').annotate(
        count=Count('id'),
        total_revenue=Sum('booking_amount')
    )
    
    # Calculate booking mode percentages for filtered period
    total_bookings_count = filtered_bookings.count()
    
    # Calculate each booking mode percentage
    oyo_count = filtered_bookings.filter(booking_mode='OYO').count()
    oyo_percentage = (oyo_count / total_bookings_count * 100) if total_bookings_count > 0 else 0
    
    ta_count = filtered_bookings.filter(booking_mode='TA').count()
    ta_percentage = (ta_count / total_bookings_count * 100) if total_bookings_count > 0 else 0
    
    ota_count = filtered_bookings.filter(booking_mode='OTA').count()
    ota_percentage = (ota_count / total_bookings_count * 100) if total_bookings_count > 0 else 0
    
    walk_in_count = filtered_bookings.filter(booking_mode='WALK_IN').count()
    walk_in_percentage = (walk_in_count / total_bookings_count * 100) if total_bookings_count > 0 else 0
    
    # Calculate revenue change compared to previous period of same duration
    previous_period_days = (end_date - start_date).days + 1
    previous_period_start = start_date - timedelta(days=previous_period_days)
    previous_period_end = start_date - timedelta(days=1)
    
    previous_period_bookings = Booking.objects.filter(
        hotel=hotel,
        booking_date__gte=previous_period_start,
        booking_date__lte=previous_period_end
    )
    
    previous_revenue = previous_period_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    current_revenue = filtered_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    
    if previous_revenue > 0:
        revenue_change = ((current_revenue - previous_revenue) / previous_revenue) * 100
    else:
        revenue_change = 100 if current_revenue > 0 else 0
    
    # Additional stats for prepaid bookings
    prepaid_booking_amount = prepaid_qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    prepaid_count = prepaid_qr_bookings.count()
    prepaid_return_qr = prepaid_qr_bookings.aggregate(total=Sum('return_qr'))['total'] or Decimal('0.00')
    
    # Calculate QR efficiency percentage (for OYO ecosystem bookings)
    total_oyo_ecosystem_bookings = filtered_bookings.filter(booking_mode__in=oyo_ecosystem_modes).count()
    if total_oyo_ecosystem_bookings > 0:
        qr_efficiency_percentage = round((qr_bookings.count() / total_oyo_ecosystem_bookings) * 100, 1)
    else:
        qr_efficiency_percentage = 0

    # Calculate QR stats by booking mode (exclude prepaid from QR amount)
    qr_stats_by_mode = {}
    for mode in oyo_ecosystem_modes:
        mode_qr_bookings = non_prepaid_qr_bookings.filter(booking_mode=mode)
        mode_not_in_qr = not_in_qr_bookings.filter(booking_mode=mode)
        
        qr_stats_by_mode[mode] = {
            'qr_count': mode_qr_bookings.count(),
            'qr_amount': mode_qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
            'not_in_qr_count': mode_not_in_qr.count(),
            'not_in_qr_amount': mode_not_in_qr.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
        }

    context = {
        'hotel': hotel,
        'today': today,
        'start_date': start_date,
        'end_date': end_date,
        'stats': {
            'today': {
                'bookings': today_bookings.count(),
                'revenue': today_revenue,
                'booking_revenue': today_booking_revenue,
                'extra_income': today_extra_income,
                'expenses': today_expenses,
                'cash': today_bookings.filter(payment_mode='CASH').aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
                'qr_due': due_to_oyo
            },
            'month': {
                'total_bookings': filtered_bookings.count(),
                'total_revenue': total_revenue,
                'total_expenses': expenses,
                'net_profit': net_profit,
                'total_rooms_used': total_rooms_used
            },
            'revenue_change': round(revenue_change, 1),
            'oyo_percentage': round(oyo_percentage, 1),
            'ta_percentage': round(ta_percentage, 1),
            'ota_percentage': round(ota_percentage, 1),
            'walk_in_percentage': round(walk_in_percentage, 1),
        },
        'qr_stats': {
            'total_qr_amount': total_qr_booking_amount,  # Total booking amount for NON-PREPAID OYO ecosystem QR bookings only
            'total_qr_returned': adjusted_qr_returned,   # Actual QR returned amount
            'total_booking_amount': non_prepaid_qr_bookings.aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00'),
            'due_to_oyo': due_to_oyo,  # Adjusted due to OYO (includes prepaid due, can be negative when OYO owes you money)
            'amount_oyo_owes': excess_amount,  # Positive amount when due_to_oyo is negative
            'qr_bookings_count': non_prepaid_qr_bookings.count(),  # Only non-prepaid bookings in QR count
            'not_in_qr_amount': not_in_qr_total_booking,
            'not_in_qr_count': not_in_qr_count,
            'not_in_qr_adjustment': not_in_qr_adjustment,
            'not_in_qr_expected_qr': not_in_qr_expected_qr,
            'prepaid_booking_amount': prepaid_booking_amount,
            'prepaid_count': prepaid_count,
            'prepaid_return_qr': prepaid_return_qr,
            'prepaid_due': prepaid_due,
            'non_prepaid_due': non_prepaid_due,
            'total_oyo_due': total_oyo_due,
            'initial_due': total_oyo_due,
            'excess_amount': excess_amount,
            'qr_efficiency_percentage': qr_efficiency_percentage,
            'by_mode': qr_stats_by_mode,  # QR stats broken down by booking mode (non-prepaid only)
        },
        'pending_qr': non_prepaid_qr_bookings.filter(return_qr__lt=F('booking_amount')).count(),
        'recent_bookings': recent_bookings,
        'booking_modes': booking_modes,
        'expenses': expenses,
        'extra_income': extra_income,
    }
    
    return render(request, 'dashboard.html', context)

def calculate_revenue_change(hotel, current_month_start):
    """Calculate revenue change compared to previous month"""
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    
    # Get current month revenue
    current_revenue = Booking.objects.filter(
        hotel=hotel,
        booking_date__gte=current_month_start
    ).aggregate(total=Sum('booking_amount'))['total'] or Decimal('0.00')
    
    # Get previous month revenue
    previous_revenue = Booking.objects.filter(
        hotel=hotel,
        booking_date__gte=previous_month_start,
        booking_date__lte=previous_month_end
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
        form = BookingForm(request.POST)
            
        if form.is_valid():
            booking = form.save(commit=False)
            booking.hotel = hotel
            
            # Auto-calculate return_qr if not_in_qr is not checked
            if not booking.not_in_qr:
                # Calculate due: number_of_rooms * hotel_qr_amount
                calculated_due = booking.number_of_rooms * hotel.qr_amount
                actual_due = min(calculated_due, booking.booking_amount)
                # Calculate QR return: booking amount - due amount
                booking.return_qr = max(Decimal('0.00'), booking.booking_amount - actual_due)
            
            booking.save()
            messages.success(request, f'Booking {booking.booking_id} created successfully!')
            return redirect('booking')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingForm()
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    date_filter = request.GET.get('date_filter', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # Get all bookings for this hotel
    bookings = Booking.objects.filter(hotel=hotel)
    
    # Apply search filter
    if search_query:
        bookings = bookings.filter(
            models.Q(booking_id__icontains=search_query) |
            models.Q(guest_name__icontains=search_query)
        )
    
    # Apply date filters - UPDATED: Use booking_date for date filtering
    if date_filter:
        today = timezone.now().date()
        if date_filter == 'today':
            bookings = bookings.filter(booking_date=today)
        elif date_filter == 'yesterday':
            yesterday = today - timedelta(days=1)
            bookings = bookings.filter(booking_date=yesterday)
        elif date_filter == 'this_week':
            start_of_week = today - timedelta(days=today.weekday())
            bookings = bookings.filter(booking_date__gte=start_of_week)
        elif date_filter == 'this_month':
            bookings = bookings.filter(booking_date__year=today.year, booking_date__month=today.month)
        elif date_filter == 'last_month':
            first_day_of_current_month = today.replace(day=1)
            last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
            first_day_of_previous_month = last_day_of_previous_month.replace(day=1)
            bookings = bookings.filter(
                booking_date__gte=first_day_of_previous_month,
                booking_date__lte=last_day_of_previous_month
            )
    
    # Apply custom date range filter
    if start_date and end_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            bookings = bookings.filter(booking_date__range=[start_date_obj, end_date_obj])
        except ValueError:
            messages.error(request, "Invalid date format. Please use YYYY-MM-DD.")
    
    # Calculate summary statistics
    total_bookings = bookings.count()
    total_amount = sum(booking.booking_amount for booking in bookings)
    total_due = sum(booking.due_to_oyo for booking in bookings)
    total_qr_return = sum(booking.return_qr for booking in bookings)
    
    # Order by booking_date (descending) and created_at (descending)
    bookings = bookings.order_by('-booking_date', '-created_at')
    
    # Pagination - 20 bookings per page
    paginator = Paginator(bookings, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Prepare booking data for JavaScript
    booking_data = {}
    for booking in bookings:  # Use all bookings for edit functionality
        booking_data[booking.id] = {
            'booking_id': booking.booking_id,
            'guest_name': booking.guest_name,
            'booking_date': booking.booking_date.strftime('%Y-%m-%d'),  # NEW
            'booking_mode': booking.booking_mode,
            'payment_mode': booking.payment_mode,
            'number_of_rooms': booking.number_of_rooms,
            'booking_amount': float(booking.booking_amount),
            'return_qr': float(booking.return_qr),
            'not_in_qr': booking.not_in_qr,
            'extra_income': float(booking.extra_income) if booking.extra_income else 0,
            'created_at': booking.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    context = {
        'form': form,
        'page_obj': page_obj,
        'hotel': hotel,
        'booking_data_json': json.dumps(booking_data),
        'search_query': search_query,
        'date_filter': date_filter,
        'start_date': start_date,
        'end_date': end_date,
        'total_bookings': total_bookings,
        'total_amount': total_amount,
        'total_due': total_due,
        'total_qr_return': total_qr_return,
    }
    
    return render(request, "bookings.html", context)

@login_required
def update_booking(request):
    if request.method == 'POST':
        try:
            booking_id = request.POST.get('id')
            booking = Booking.objects.get(id=booking_id, hotel__user=request.user)
            
            # Update booking fields
            booking.booking_id = request.POST.get('booking_id')
            booking.guest_name = request.POST.get('guest_name')
            
            # Parse and update booking date
            booking_date_str = request.POST.get('booking_date')
            if booking_date_str:
                booking.booking_date = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
            
            booking.booking_mode = request.POST.get('booking_mode')
            booking.payment_mode = request.POST.get('payment_mode')
            booking.number_of_rooms = int(request.POST.get('number_of_rooms', 1))
            booking.booking_amount = Decimal(request.POST.get('booking_amount'))
            booking.return_qr = Decimal(request.POST.get('return_qr'))
            booking.not_in_qr = request.POST.get('not_in_qr') == 'on'
            
            # Auto-calculate return_qr if not_in_qr is not checked
            if not booking.not_in_qr:
                # Calculate due: number_of_rooms * hotel_qr_amount
                calculated_due = booking.number_of_rooms * booking.hotel.qr_amount
                actual_due = min(calculated_due, booking.booking_amount)
                # Calculate QR return: booking amount - due amount
                booking.return_qr = max(Decimal('0.00'), booking.booking_amount - actual_due)
            else:
                booking.return_qr = Decimal('0.00')
            
            booking.save()
            messages.success(request, f'Booking {booking.booking_id} updated successfully!')
        except Booking.DoesNotExist:
            messages.error(request, 'Booking not found.')
        except Exception as e:
            messages.error(request, f'Error updating booking: {str(e)}')
    
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
    except Exception as e:
        messages.error(request, f"An error occurred while deleting the booking: {str(e)}")
    
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
    
    # Get all extra incomes for this hotel, ordered by date first, then created_at
    incomes = ExtraIncome.objects.filter(hotel=hotel).order_by('-date', '-created_at')
    
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
        
        # Update date field
        date_value = request.POST.get('date')
        if date_value:
            income_instance.date = date_value
        
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
        messages.error(request, "Invalid amount or date format.")
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
    
    # Get all expenses for this hotel, ordered by date first, then created_at
    expenses = DailyExpense.objects.filter(hotel=hotel).order_by('-date', '-created_at')
    
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
        
        # Update date field
        date_value = request.POST.get('date')
        if date_value:
            expense_instance.date = date_value
        
        expense_instance.save()
        
        messages.success(request, f'Expense updated successfully!')
        return redirect('expenses')
            
    except Hotel.DoesNotExist:
        messages.error(request, "You don't have permission to edit this expense.")
        return redirect('expenses')
    except ValueError as e:
        messages.error(request, "Invalid amount or date format.")
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
@login_required
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
    
    # Get filtered bookings - UPDATED: Use booking_date instead of created_at
    simple_bookings = SimpleBooking.objects.filter(
        hotel=hotel,
        booking_date__gte=start_date,
        booking_date__lte=end_date
    ).order_by('-booking_date', '-created_at')
    
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
            booking_date__gte=month_start,
            booking_date__lte=month_end
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
            booking_date=day_date
        )
        day_revenue = day_bookings.aggregate(Sum('booking_amount'))['booking_amount__sum'] or Decimal('0.00')
        day_extra_income = day_bookings.aggregate(Sum('extra_income'))['extra_income__sum'] or Decimal('0.00')
        daily_data.append(float(day_revenue + day_extra_income))
    
    if request.method == 'POST':
        # Handle form submission for new booking
        guest_name = request.POST.get('guest_name')
        booking_date = request.POST.get('booking_date')  # NEW: Get booking date
        booking_amount = request.POST.get('booking_amount')
        extra_income = request.POST.get('extra_income', '0.00')
        
        # Validate and create booking
        try:
            booking = SimpleBooking(
                hotel=hotel,
                guest_name=guest_name,
                booking_date=datetime.strptime(booking_date, '%Y-%m-%d').date(),  # NEW: Parse booking date
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
        booking.booking_date = datetime.strptime(request.POST.get('booking_date'), '%Y-%m-%d').date()  # NEW: Update booking date
        booking.booking_amount = request.POST.get('booking_amount')
        booking.extra_income = request.POST.get('extra_income', '0.00')
        
        try:
            booking.save()
            messages.success(request, 'Booking updated successfully!')
            return redirect('blackroom')
        except Exception as e:
            messages.error(request, f'Error updating booking: {str(e)}')
            return redirect('blackroom')
    
    return redirect('blackroom')

def delete_simple_booking(request, booking_id):
    booking = get_object_or_404(SimpleBooking, id=booking_id)
    
    try:
        booking.delete()
        messages.success(request, 'Booking deleted successfully!')
    except Exception as e:
        messages.error(request, f'Error deleting booking: {str(e)}')
    
    return redirect('blackroom')