from django.urls import path

from . import views

app_name = "sales"
urlpatterns = [
    path("", views.daily_list, name="daily"),
    path("daily/", views.daily_list, name="daily_list"),
    path("daily/today/", views.daily_today, name="daily_today"),
    path("daily/<str:day>/", views.daily_edit, name="daily_edit"),
    path("cashups/", views.cashup_list, name="cashups"),
    path("cashup/new/", views.cashup_new, name="cashup_new"),
    path("cashup/<int:pk>/", views.cashup_detail, name="cashup"),
    path("cashup/<int:pk>/edit/", views.cashup_edit, name="cashup_edit"),
    path("cashup/<int:pk>/print/", views.cashup_print, name="cashup_print"),
    path("cashup/<int:pk>/signoff/", views.cashup_signoff, name="cashup_signoff"),
    path("cashup/<int:pk>/delete/", views.cashup_delete, name="cashup_delete"),
    path("expenses/", views.expense_list, name="expenses"),
    path("expenses/new/", views.expense_edit, name="expense_new"),
    path("expenses/<int:pk>/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),
    path("products/", views.daysales_list, name="daysales_list"),
    path("products/new/", views.daysales_new, name="daysales_new"),
    path("products/<int:pk>/", views.daysales_detail, name="daysales"),
    path("products/<int:pk>/edit/", views.daysales_edit, name="daysales_edit"),
    path("products/<int:pk>/delete/", views.daysales_delete, name="daysales_delete"),
    path("report/", views.report, name="report"),
    path("over-short/", views.cashier_report, name="cashier_report"),
    path("setup/", views.setup_lists, name="setup"),
    path("setup/<str:kind>/new/", views.setup_edit, name="setup_new"),
    path("setup/<str:kind>/<int:pk>/", views.setup_edit, name="setup_edit"),
]
