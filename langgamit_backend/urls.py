# langgam_it/urls.py  (your project's root URLconf)
#
# Mount the API routes under /api/
# All auth endpoints will be available at:
#   /api/auth/register/
#   /api/auth/token/
#   /api/auth/token/refresh/
#   /api/auth/me/

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django admin (keep for superuser management in dev)
    path("admin/", admin.site.urls),

    # All API routes
    path("api/", include("api.urls")),
]