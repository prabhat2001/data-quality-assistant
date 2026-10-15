from django.apps import AppConfig


class QualityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    default = True
    name = "quality"
    verbose_name = "Data quality"
