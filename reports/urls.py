from django.urls import path

from . import accountant_views, views

app_name = "reports"
urlpatterns = [
    path("", views.month_end_view, name="month_end"),
    path("print/", views.month_end_print, name="month_end_print"),
    path("stock/", views.stock_results_view, name="stock"),
    path("accountant/", accountant_views.accountant_print, name="accountant"),
    path("accountant/excel/", accountant_views.accountant_excel, name="accountant_excel"),
    path("archive/", views.archive_view, name="archive"),
    path("archive/lock/", views.lock_month, name="lock"),
    path("archive/<int:pk>/", views.archive_edit, name="archive_edit"),
]
