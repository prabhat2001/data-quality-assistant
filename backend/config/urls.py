from django.urls import include, path

from quality.views import not_found, root, server_error

handler404 = not_found
handler500 = server_error

urlpatterns = [
    path("", root),
    path("api/", include("quality.urls")),
]
