from django.urls import path

from quality import views

urlpatterns = [
    path("health", views.health),
    path("tables", views.tables),
    path("tables/<str:schema_name>/<str:table_name>", views.table_detail),
    path("tables/<str:schema_name>/<str:table_name>/suggestions", views.suggestions),
    path("rules", views.rules),
    path("rules/natural-language", views.natural_language),
    path("rules/<str:rule_id>", views.rule_detail),
    path("runs", views.runs),
    path("runs/latest", views.latest_run),
    path("runs/<str:run_id>", views.run_detail),
]
