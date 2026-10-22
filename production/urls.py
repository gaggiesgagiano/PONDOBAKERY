from django.urls import path

from . import views

app_name = "production"
urlpatterns = [
    path("", views.plan_list, name="plans"),
    path("new/", views.plan_new, name="plan_new"),
    path("<int:pk>/", views.plan_detail, name="plan"),
    path("<int:pk>/edit/", views.plan_edit, name="plan_edit"),
    path("<int:pk>/status/", views.plan_status, name="plan_status"),
    path("<int:pk>/delete/", views.plan_delete, name="plan_delete"),
    path("<int:pk>/print/<str:kind>/", views.plan_print, name="plan_print"),
    path("waste/", views.waste_list, name="waste_list"),
    path("waste/new/", views.waste_new, name="waste_new"),
    path("waste/summary/", views.waste_summary, name="waste_summary"),
    path("waste/<int:pk>/", views.waste_detail, name="waste"),
    path("waste/<int:pk>/edit/", views.waste_edit, name="waste_edit"),
    path("waste/<int:pk>/signoff/", views.waste_signoff, name="waste_signoff"),
]
