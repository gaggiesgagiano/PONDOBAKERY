from django.urls import path

from . import views

app_name = "fiscal"
urlpatterns = [
    path("", views.home, name="home"),
    path("do/", views.act, name="act"),
    path("retry/<int:pk>/", views.retry_one, name="retry"),
    path("setup/", views.setup, name="setup"),
    path("journal/", views.journal, name="journal"),
    path("journal/<int:pk>/", views.call_detail, name="call"),
]
