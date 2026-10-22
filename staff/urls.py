from django.urls import path

from . import files, views

app_name = "staff"
urlpatterns = [
    path("", views.staff_list, name="people"),
    path("new/", views.staff_edit, name="person_new"),
    path("<int:pk>/", views.staff_detail, name="person"),
    path("<int:pk>/edit/", views.staff_edit, name="person_edit"),
    path("<int:pk>/photo/", files.photo, name="photo"),
    path("<int:pk>/photo/change/", files.photo_change, name="photo_change"),
    path("<int:pk>/papers/add/", files.paper_add, name="paper_add"),
    path("<int:pk>/file/print/", files.print_file, name="file_print"),
    path("<int:pk>/card/print/", files.print_cards, name="card_print"),
    path("papers/<int:pk>/", files.paper_open, name="paper"),
    path("papers/<int:pk>/edit/", files.paper_edit, name="paper_edit"),
    path("papers/<int:pk>/hard/", files.paper_hard, name="paper_hard"),
    path("papers/<int:pk>/delete/", files.paper_delete, name="paper_delete"),
    path("files/", files.overview, name="files"),
    path("files/settings/", files.file_settings, name="file_settings"),
    path("files/numbers/", files.give_numbers, name="give_numbers"),
    path("files/print/", files.print_file, name="files_print"),
    path("cards/print/", files.print_cards, name="cards_print"),
    path("<int:pk>/advance/", views.advance_add, name="advance_add"),
    path("advance/<int:pk>/delete/", views.advance_delete, name="advance_delete"),
    path("<int:pk>/leave/", views.leave_add, name="leave_add"),
    path("leave/<int:pk>/delete/", views.leave_delete, name="leave_delete"),
    path("payroll/", views.payrun_list, name="payruns"),
    path("payroll/new/", views.payrun_new, name="payrun_new"),
    path("payroll/settings/", views.payroll_settings, name="settings"),
    path("payroll/<int:pk>/", views.payrun_detail, name="payrun"),
    path("payroll/<int:pk>/edit/", views.payrun_edit, name="payrun_edit"),
    path("payroll/<int:pk>/status/", views.payrun_status, name="payrun_status"),
    path("payroll/<int:pk>/delete/", views.payrun_delete, name="payrun_delete"),
    path("payroll/<int:pk>/payslips/", views.payslips, name="payslips"),
    path("payroll/<int:pk>/payslips/<int:emp>/", views.payslips, name="payslip"),
    path("payroll/<int:pk>/summary/", views.payrun_summary, name="payrun_summary"),
]
