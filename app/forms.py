from django import forms
from .models import *

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['booking_id', 'guest_name', 'booking_date', 'booking_mode', 'payment_mode', 
                  'number_of_rooms', 'booking_amount', 'return_qr', 'not_in_qr']
        widgets = {
            'booking_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'booking_id': forms.TextInput(attrs={'class': 'form-control'}),
            'guest_name': forms.TextInput(attrs={'class': 'form-control'}),
            'booking_mode': forms.Select(attrs={'class': 'form-control'}),
            'payment_mode': forms.Select(attrs={'class': 'form-control'}),
            'number_of_rooms': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'booking_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'return_qr': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'not_in_qr': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
class ExtraIncomeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.hotel = kwargs.pop('hotel', None)
        super().__init__(*args, **kwargs)
        
        if self.hotel:
            # Filter bookings to only those belonging to the hotel
            self.fields['booking'].queryset = Booking.objects.filter(hotel=self.hotel)
    
    class Meta:
        model = ExtraIncome
        fields = ['booking', 'source', 'amount', 'description']
        widgets = {
            'booking': forms.Select(attrs={'class': 'form-control'}),
            'source': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional description'}),
        }
        labels = {
            'booking': 'Associated Booking (Optional)',
            'source': 'Income Source',
            'amount': 'Amount (₹)',
            'description': 'Description',
        }



class DailyExpenseForm(forms.ModelForm):
    class Meta:
        model = DailyExpense
        fields = ['expense_type', 'amount', 'description']
        widgets = {
            'expense_type': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter expense description'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'