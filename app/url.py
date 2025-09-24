from django.contrib import admin
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
path('admin/', admin.site.urls),
path('', views.login_view, name='login'),
path('logout/', views.logout_view, name='logout'),
path('bookings/delete/<int:booking_id>/', views.delete_booking, name='delete_booking'),
    # Dashboard URL
path('dashboard/', views.dashboard, name='dashboard'),
path('update-booking/', views.update_booking, name='update_booking'),

path('booking/',views.booking,name='booking'),
path('extra-income/', views.extra_income, name='extra_income'),
path('update-extra-income/', views.update_extra_income, name='update_extra_income'),
path('delete-extra-income/<int:income_id>/', views.delete_extra_income, name='delete_extra_income'),
path('expenses/', views.expenses, name='expenses'),
path('blackroom/',views.blackroom,name='blackroom'),
path('edit-simple-booking/<int:booking_id>/', views.edit_simple_booking, name='edit_simple_booking'),
path('delete-simple-booking/<int:booking_id>/', views.delete_simple_booking, name='delete_simple_booking'),
path('expenses/update/', views.update_expense, name='update_expense'),
path('expenses/delete/<int:expense_id>/', views.delete_expense, name='delete_expense'),


]