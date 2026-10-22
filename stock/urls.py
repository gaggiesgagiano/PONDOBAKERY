from django.urls import path

from . import views

app_name = "stock"
urlpatterns = [
    path("", views.stock_home, name="home"),
    path("suppliers/", views.supplier_list, name="suppliers"),
    path("suppliers/new/", views.supplier_edit, name="supplier_new"),
    path("suppliers/<int:pk>/", views.supplier_edit, name="supplier_edit"),
    path("orders/", views.order_list, name="orders"),
    path("orders/new/", views.order_edit, name="order_new"),
    path("orders/<int:pk>/", views.order_detail, name="order"),
    path("orders/<int:pk>/edit/", views.order_edit, name="order_edit"),
    path("orders/<int:pk>/print/", views.order_print, name="order_print"),
    path("orders/<int:pk>/status/", views.order_status, name="order_status"),
    path("orders/<int:pk>/whatsapp/", views.order_whatsapp, name="order_whatsapp"),
    path("grv/", views.grv_list, name="grvs"),
    path("grv/new/", views.grv_edit, name="grv_new"),
    path("grv/<int:pk>/", views.grv_detail, name="grv"),
    path("grv/<int:pk>/edit/", views.grv_edit, name="grv_edit"),
    path("counts/", views.count_list, name="counts"),
    path("counts/new/", views.count_new, name="count_new"),
    path("counts/<int:pk>/", views.count_detail, name="count"),
    path("counts/<int:pk>/edit/", views.count_edit, name="count_edit"),
    path("counts/<int:pk>/sheet/", views.count_sheet, name="count_sheet"),
    path("counts/<int:pk>/variance/", views.count_variance, name="count_variance"),
    path("counts/settings/", views.count_settings, name="count_settings"),
]
