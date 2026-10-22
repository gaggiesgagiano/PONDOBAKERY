from django.urls import path

from . import views

app_name = "costing"
urlpatterns = [
    path("", views.recipe_list, name="recipes"),
    path("new/", views.recipe_edit, name="recipe_new"),
    path("<int:pk>/", views.recipe_detail, name="recipe"),
    path("<int:pk>/edit/", views.recipe_edit, name="recipe_edit"),
    path("<int:pk>/archive/", views.recipe_archive, name="recipe_archive"),
    path("<int:pk>/photo/", views.recipe_photo, name="recipe_photo"),
    path("<int:pk>/print/<str:kind>/", views.recipe_print, name="recipe_print"),
    path("ingredients/", views.ingredient_list, name="ingredients"),
    path("ingredients/new/", views.ingredient_edit, name="ingredient_new"),
    path("ingredients/<int:pk>/", views.ingredient_detail, name="ingredient"),
    path("ingredients/<int:pk>/edit/", views.ingredient_edit, name="ingredient_edit"),
    path("prices/", views.price_list, name="prices"),
    path("prices/cards/", views.price_cards, name="cards"),
    path("prices/cards/print/", views.price_cards_print, name="cards_print"),
    path("lists/", views.lists_view, name="lists"),
]
