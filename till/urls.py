from django.urls import path

from . import views

app_name = "till"
urlpatterns = [
    path("", views.start, name="start"),
    path("<int:pk>/", views.screen, name="screen"),
    path("<int:pk>/sell/", views.sell, name="sell"),
    path("<int:pk>/sales/", views.shift_sales, name="sales"),
    path("<int:pk>/refund/<int:sale_pk>/", views.refund, name="refund"),
    path("<int:pk>/close/", views.close, name="close"),
    path("receipt/<int:pk>/", views.receipt, name="receipt"),
    path("<int:pk>/move/<str:kind>/", views.move, name="move"),
    path("slip/<int:pk>/", views.move_slip, name="move_slip"),
]
