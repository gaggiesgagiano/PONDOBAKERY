from django.urls import path

from . import views

app_name = "money"
urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/new/", views.account_edit, name="account_new"),
    path("accounts/<int:pk>/edit/", views.account_edit, name="account_edit"),
    path("accounts/<int:pk>/", views.book, name="book"),
    path("accounts/<int:pk>/check/", views.bank_check, name="bank_check"),
    path("entries/new/", views.entry_edit, name="entry_new"),
    path("entries/<int:pk>/", views.entry_edit, name="entry_edit"),
    path("entries/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("suppliers/", views.creditors_view, name="creditors"),
    path("suppliers/<int:pk>/", views.statement, name="statement"),
    path("suppliers/pay/", views.pay, name="pay"),
    path("payments/<int:pk>/", views.payment, name="payment"),
    path("payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("vat/", views.vat, name="vat"),
    path("balance-sheet/", views.balance_sheet_view, name="balance"),
]
