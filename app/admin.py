from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Sum, Count
from .models import *

admin.site.register(Hotel)
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        'booking_id', 'hotel', 'guest_name', 
        'booking_mode', 'payment_mode', 'booking_amount', 
        'return_qr', 'due_amount', 'created_at','extra_income'
    ]
    list_filter = ['booking_mode', 'hotel', 'payment_mode', 'created_at']
    search_fields = ['booking_id', 'guest_name', 'hotel__hotel_name']
    readonly_fields = ['created_at', 'due_amount']
    date_hierarchy = 'created_at'
    
    def due_amount(self, obj):
        return f"₹{obj.due_to_oyo:,.2f}"
    due_amount.short_description = 'Due to OYO'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            hotel = Hotel.objects.get(user=request.user)
            return qs.filter(hotel=hotel)
        except Hotel.DoesNotExist:
            return qs.none()

@admin.register(ExtraIncome)
class ExtraIncomeAdmin(admin.ModelAdmin):
    list_display = ['hotel','booking','source', 'amount', 'description', 'created_at']
    list_filter = ['source', 'created_at']
    search_fields = ['description']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # ExtraIncome no longer has hotel relationship, so we can't filter by hotel
        return qs

@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ['expense_type', 'amount', 'description', 'created_at']
    list_filter = ['expense_type', 'created_at']
    search_fields = ['description']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # DailyExpense no longer has hotel relationship, so we can't filter by hotel
        return qs

@admin.register(MonthlyReport)
class MonthlyReportAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'month', 'total_revenue', 'total_expenses', 'net_profit')
    list_filter = ('month', 'hotel')
    readonly_fields = ('created_at', 'updated_at')
    search_fields = ('hotel__hotel_name',)
    date_hierarchy = 'month'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('hotel', 'month')
        }),
        ('Financial Summary', {
            'fields': (
                'total_revenue', 'total_expenses', 'net_profit',
                'total_extra_income', 'total_oyo_due', 'total_qr_returned'
            )
        }),
        ('Booking Statistics', {
            'fields': (
                'total_bookings', 'oyo_bookings', 'ota_bookings', 'walk_in_bookings',
                'cash_payments', 'upi_payments', 'prepaid_payments'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

admin.site.register(SimpleBooking)