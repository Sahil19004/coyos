from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal

class Hotel(models.Model):
    """Hotel model representing each hotel user"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    hotel_name = models.CharField(max_length=200)
    hotel_code = models.CharField(max_length=50, unique=True)
    qr_amount=models.IntegerField(default=0,null=True)
    address = models.TextField()
    contact_number = models.CharField(max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.hotel_name} ({self.hotel_code})"
    
    class Meta:
        verbose_name = "Hotel"
        verbose_name_plural = "Hotels"

class Booking(models.Model):
    """Individual booking entries"""
    BOOKING_MODE_CHOICES = [
        ('OYO', 'OYO'),
        ('TA', 'TA'),
        ('OTA', 'OTA'),
        ('WALK_IN', 'Walk-in'),
    ]
    
    PAYMENT_MODE_CHOICES = [
        ('CASH', 'Cash'),
        ('UPI', 'UPI'),
        ('PREPAID', 'Prepaid'),
    ]
    
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True)
    booking_id = models.CharField(max_length=100)
    guest_name = models.CharField(max_length=200)
    booking_mode = models.CharField(max_length=10, choices=BOOKING_MODE_CHOICES)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES)
    number_of_rooms = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    booking_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    return_qr = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    created_at = models.DateTimeField(auto_now_add=True)
    extra_income = models.CharField(max_length=10, null=True, blank=True)
    not_in_qr = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.booking_id} - {self.guest_name}"
    
    @property
    def due_to_oyo(self):
        """Calculate due amount for ALL booking types based on number of rooms"""
        if self.not_in_qr:
            return Decimal('0.00')
        
        # Calculate due as: number_of_rooms * hotel_qr_amount
        if hasattr(self, 'hotel') and self.hotel and self.hotel.qr_amount:
            due_amount = self.number_of_rooms * self.hotel.qr_amount
            # Ensure due amount doesn't exceed booking amount
            return min(due_amount, self.booking_amount)
        return Decimal('0.00')
    
    class Meta:
        verbose_name = "Booking"
        verbose_name_plural = "Bookings"
        ordering = ['-created_at']
class ExtraIncome(models.Model):
    """Extra income sources"""
    INCOME_SOURCE_CHOICES = [
        ('KITCHEN', 'Kitchen / Food'),
        ('MINI_BAR', 'Mini Bar'),
        ('PARKING', 'Parking'),
        ('OTHER', 'Other'),
    ]
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE,null=True,blank=True)
    booking=models.ForeignKey(Booking,on_delete=models.CASCADE,null=True,blank=True)
    source = models.CharField(max_length=20, choices=INCOME_SOURCE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    description = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_source_display()} - ₹{self.amount}"
    
    class Meta:
        verbose_name = "Extra Income"
        verbose_name_plural = "Extra Incomes"

class DailyExpense(models.Model):
    """Daily expenses"""
    EXPENSE_TYPE_CHOICES = [
        ('STAFF_SALARY', 'Staff Salary / Wages'),
        ('KITCHEN_GROCERY', 'Kitchen / Grocery'),
        ('ELECTRICITY_WATER', 'Electricity / Water Bill'),
        ('MAINTENANCE', 'Maintenance'),
        ('OTHER', 'Other'),
    ]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='expenses')
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    description = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_expense_type_display()} - ₹{self.amount}"
    
    class Meta:
        verbose_name = "Daily Expense"
        verbose_name_plural = "Daily Expenses"
class MonthlyReport(models.Model):
    """Monthly aggregated reports"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='monthly_reports')
    month = models.DateField()  # First day of the month
    total_bookings = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_oyo_due = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_cash_collected = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_qr_returned = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_extra_income = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Booking mode breakdown
    oyo_bookings = models.IntegerField(default=0)
    ota_bookings = models.IntegerField(default=0)
    walk_in_bookings = models.IntegerField(default=0)
    
    # Payment mode breakdown
    cash_payments = models.IntegerField(default=0)
    upi_payments = models.IntegerField(default=0)
    prepaid_payments = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.hotel.hotel_name} - {self.month.strftime('%B %Y')}"
    
    class Meta:
        unique_together = ['hotel', 'month']
        verbose_name = "Monthly Report"
        verbose_name_plural = "Monthly Reports"
        ordering = ['-month']


class SimpleBooking(models.Model):
    """Simplified booking model for display purposes"""
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True)
    guest_name = models.CharField(max_length=200)
    booking_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    extra_income = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Optional: Add a reference to the original booking if needed
    original_booking = models.OneToOneField(Booking, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.guest_name} - {self.hotel.name if self.hotel else 'No Hotel'}"