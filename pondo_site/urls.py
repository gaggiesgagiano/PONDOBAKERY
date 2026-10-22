from django.conf import settings
from django.contrib.auth import views as auth_views
from core import cards as core_cards
from django.urls import include, path, re_path
from django.views.static import serve

from core.setup_view import setup
from core.views import LoginView

urlpatterns = [
    path("setup/", setup, name="setup"),
    path("login/", LoginView.as_view(), name="login"),
    path("login/card/", core_cards.card_login, name="card_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("core.urls")),
    path("recipes/", include("costing.urls")),
    path("production/", include("production.urls")),
    path("stock/", include("stock.urls")),
    path("sales/", include("sales.urls")),
    path("till/", include("till.urls")),
    path("fiscal/", include("fiscal.urls")),
    path("staff/", include("staff.urls")),
    path("reports/", include("reports.urls")),
    path("invoices/", include("invoices.urls")),
    path("equipment/", include("equipment.urls")),
    path("money/", include("money.urls")),
    # The program runs on one laptop, so Django serves its own static files.
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATICFILES_DIRS[0]}),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
