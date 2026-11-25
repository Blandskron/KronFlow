from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def healthz(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthz, name="health"),
    path("healthz/", healthz, name="healthz"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/contact/", include("apps.contact.urls")),
    path("api/v1/tenants/", include("apps.tenants.urls")),
    path("api/v1/rbac/", include("apps.rbac.urls")),
    path("api/v1/sessions/", include("apps.sessions.urls")),
    path("api/v1/audit/", include("apps.audit.urls")),
    path("api/v1/security/", include("apps.security.urls")),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    re_path(r"^.*$", RedirectView.as_view(url="/api/docs/", permanent=False), name="api-docs-fallback"),
]
