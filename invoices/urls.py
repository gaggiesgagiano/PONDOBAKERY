from django.urls import path

from . import deliveries, drivers, views

app_name = "invoices"
urlpatterns = [
    path("", views.doc_list, name="list"),
    path("new/", views.doc_edit, name="new"),
    path("<int:pk>/", views.doc_detail, name="doc"),
    path("<int:pk>/edit/", views.doc_edit, name="edit"),
    path("<int:pk>/print/", views.doc_print, name="print"),
    path("<int:pk>/status/", views.doc_status, name="status"),
    path("<int:pk>/convert/", views.doc_convert, name="convert"),
    path("<int:pk>/delete/", views.doc_delete, name="delete"),
    path("deliveries/", deliveries.delivery_list, name="deliveries"),
    path("deliveries/new/", deliveries.delivery_edit, name="delivery_new"),
    path("deliveries/<int:pk>/", deliveries.delivery_detail, name="delivery"),
    path("deliveries/<int:pk>/edit/", deliveries.delivery_edit, name="delivery_edit"),
    path("deliveries/<int:pk>/status/", deliveries.delivery_status, name="delivery_status"),
    path("deliveries/<int:pk>/note/", deliveries.delivery_note, name="delivery_note"),
    path("drivers/", drivers.driver_list, name="drivers"),
    path("drivers/new/", drivers.driver_edit, name="driver_new"),
    path("drivers/cards/", drivers.driver_cards, name="driver_cards"),
    path("drivers/<int:pk>/", drivers.driver_detail, name="driver"),
    path("drivers/<int:pk>/edit/", drivers.driver_edit, name="driver_edit"),
    path("drivers/<int:pk>/card/", drivers.driver_cards, name="driver_card"),
    path("drivers/<int:pk>/photo/<str:which>/", drivers.driver_photo, name="driver_photo"),
    path("drivers/<int:pk>/photo/<str:which>/change/", drivers.driver_photo_change, name="driver_photo_change"),
    path("customers/", views.customer_list, name="customers"),
    path("customers/new/", views.customer_edit, name="customer_new"),
    path("customers/<int:pk>/", views.customer_edit, name="customer_edit"),
]
