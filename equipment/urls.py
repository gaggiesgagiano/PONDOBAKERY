from django.urls import path

from . import views

app_name = "equipment"
urlpatterns = [
    path("", views.register, name="register"),
    path("new/", views.item_edit, name="item_new"),
    path("<int:pk>/", views.item_edit, name="item"),
    path("count/", views.count_view, name="count"),
    path("depreciation/", views.depreciation, name="depreciation"),
    path("lists/", views.lists, name="lists"),
]
