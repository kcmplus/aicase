from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from management_api import views
from management_api.orders import StoreOrders, StoreOrder, StoreOrderAction
from management_api.ai_service import AIServiceSettingsView, AIServiceCheckView

router = DefaultRouter()
router.register("ai-examples", views.AIExampleViewSet)
for name, view in [("brands", views.BrandViewSet), ("phone-models", views.PhoneModelViewSet), ("graphics", views.GraphicViewSet), ("designs", views.DesignTemplateViewSet), ("ai-styles", views.AIStyleViewSet), ("plans", views.PricingPlanViewSet), ("orders", views.OrderViewSet), ("users", views.UserViewSet), ("roles", views.RoleViewSet), ("audit-logs", views.AuditViewSet)]:
    router.register(name, view)
urlpatterns = [
    path("api/v1/store/orders/", StoreOrders.as_view()),
    path("api/v1/store/orders/<uuid:reference>/", StoreOrder.as_view()),
    path("api/v1/store/orders/<uuid:reference>/actions/", StoreOrderAction.as_view()),
    path("api/health/", lambda request: JsonResponse({"status": "ok"})),
    path("api/v1/auth/csrf/", views.csrf),
    path("api/v1/auth/login/", views.LoginView.as_view()),
    path("api/v1/auth/session/", views.SessionView.as_view()),
    path("api/v1/auth/password/", views.PasswordView.as_view()),
    path("api/v1/admin/dashboard/", views.DashboardView.as_view()),
    path("api/v1/admin/ai-service/", AIServiceSettingsView.as_view()),
    path("api/v1/admin/ai-service/check/", AIServiceCheckView.as_view()),
    path("api/v1/admin/permissions/", views.PermissionsView.as_view()),
    path("api/v1/admin/uploads/", views.UploadView.as_view()),
    path("api/v1/admin/", include(router.urls)),
    path("api/v1/catalog/", views.public_catalog),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
