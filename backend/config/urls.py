from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from management_api import views
from management_api.phone_colors import PhoneColorViewSet
from management_api.inventory import (ConnectionViewSet, DeviceViewSet, ProductViewSet,
                                     StockViewSet, RunViewSet, InventoryOptions)
from management_api.orders import StoreOrders, StoreOrder, StoreOrderAction, OrderFulfillment, StoreOrderProgress
from management_api.ai_service import AIServiceSettingsView, AIServiceCheckView
from management_api.ai_generation import AIAccountView, AIRenders, AIRenderDetail, AIRenderImage
from management_api.ai_reporting import AIUsageView, AICallLogsView, AIRenderCostView, AIAdminImageView
from management_api.customer_auth import CustomerView, SendCode, VerifyCode, CustomerCredits
from management_api.social_login import SocialSettings, SocialStart, SocialCallback
from management_api.mail_service import MailSettings, MailTest, RegistrationSettings

from management_api.customers import CustomerViewSet
from management_api.stripe_payments import StripeSettings, StripeWebhook
from management_api.payments import PublicPaymentConfig, PaymentCheckout
from management_api.airwallex_payments import AirwallexSettings, AirwallexWebhook

from management_api.refunds import AdminRefund
from management_api.order_stations import OrderStations, public_print_stations
from management_api.device_info import public_device_info
from management_api.supplier_orders import OrderTarget, OrderFiles, ConfirmSupplierPrint, SupplierFile, SupplierImage, FulfillmentConfig, RetrySupplierOrder
from management_api.terminal_orders import RetiredTerminalAPI
from management_api.direct_terminal import DirectPoll, DirectPreview

router = DefaultRouter()
router.register('phone-colors', PhoneColorViewSet)
router.register('device-connections', ConnectionViewSet)
router.register('devices', DeviceViewSet)
router.register('inventory/products', ProductViewSet)
router.register('inventory/stocks', StockViewSet)
router.register('inventory/sync-runs', RunViewSet)
router.register("customers", CustomerViewSet)
router.register("ai-examples", views.AIExampleViewSet)
for name, view in [("brands", views.BrandViewSet), ("phone-models", views.PhoneModelViewSet), ("graphics", views.GraphicViewSet), ("designs", views.DesignTemplateViewSet), ("ai-styles", views.AIStyleViewSet), ("plans", views.PricingPlanViewSet), ("orders", views.OrderViewSet), ("users", views.UserViewSet), ("roles", views.RoleViewSet), ("audit-logs", views.AuditViewSet)]:
    router.register(name, view)
urlpatterns = [
    path('api/v1/debug-terminal/poll/', DirectPoll.as_view()),
    path('api/v1/debug-terminal/orders/<uuid:reference>/preview.png', DirectPreview.as_view()),
    path('api/v1/store/device-info/', public_device_info),
    path('api/v1/store/phone-models/', views.public_phone_models),
    path('api/v1/admin/inventory/options/', InventoryOptions.as_view()),
    path("api/v1/admin/orders/<int:pk>/refund/", AdminRefund.as_view()),
    path("api/v1/store/customer/credits/", CustomerCredits.as_view()),
    path("api/v1/store/customer/", CustomerView.as_view()),
    path("api/v1/store/customer/social/<str:provider>/start/", SocialStart.as_view()),
    path("api/v1/store/customer/social/<str:provider>/callback/", SocialCallback.as_view()),
    path("api/v1/admin/social-login/<str:provider>/", SocialSettings.as_view()),
    path("api/v1/store/customer/send-code/", SendCode.as_view()),
    path("api/v1/store/customer/verify/", VerifyCode.as_view()),
    path("api/v1/admin/registration/", RegistrationSettings.as_view()),
    path("api/v1/admin/mail/", MailSettings.as_view()),
    path("api/v1/admin/mail/test/", MailTest.as_view()),
    path("api/v1/admin/airwallex/", AirwallexSettings.as_view()),
    path("api/v1/payments/airwallex/webhook/", AirwallexWebhook.as_view()),
    path("api/v1/admin/stripe/", StripeSettings.as_view()),
    path("api/v1/store/payment-config/", PublicPaymentConfig.as_view()),
    path("api/v1/store/orders/<uuid:reference>/checkout/", PaymentCheckout.as_view()),
    path("api/v1/payments/stripe/webhook/", StripeWebhook.as_view()),
    path("api/v1/store/ai-account/", AIAccountView.as_view()),
    path("api/v1/store/ai-renders/", AIRenders.as_view()),
    path("api/v1/store/ai-renders/<uuid:reference>/", AIRenderDetail.as_view()),
    path("api/v1/store/ai-renders/<uuid:reference>/image/", AIRenderImage.as_view()),
    path("api/v1/store/orders/", StoreOrders.as_view()),
    path("api/v1/store/fulfillment-config/", FulfillmentConfig.as_view()),
    path("api/v1/store/orders/<uuid:reference>/device/", OrderTarget.as_view()),
    path("api/v1/store/orders/<uuid:reference>/print-files/", OrderFiles.as_view()),
    path("api/v1/store/orders/<uuid:reference>/retry-dispatch/", RetrySupplierOrder.as_view()),
    path("api/v1/store/orders/<uuid:reference>/confirm-print/", ConfirmSupplierPrint.as_view()),
    path("api/v1/supplier-order-files/<str:token>/", SupplierFile.as_view()),
    path("api/v1/supplier-images/<uuid:token>/<str:kind>.png", SupplierImage.as_view()),
    path("api/v1/store/orders/<uuid:reference>/fulfillment/", OrderFulfillment.as_view()),
    path("api/v1/terminal/orders/", RetiredTerminalAPI.as_view()),
    path("api/v1/terminal/orders/<uuid:reference>/claim/", RetiredTerminalAPI.as_view()),
    path("api/v1/terminal/orders/<uuid:reference>/observe/", RetiredTerminalAPI.as_view()),
    path("api/v1/store/print-stations/", public_print_stations),
    path("api/v1/store/orders/<uuid:reference>/stations/", OrderStations.as_view()),
    path("api/v1/store/orders/<uuid:reference>/progress/", StoreOrderProgress.as_view()),
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
    path("api/v1/admin/ai-usage/", AIUsageView.as_view()),
    path("api/v1/admin/ai-renders/", AICallLogsView.as_view()),
    path("api/v1/admin/ai-renders/<uuid:reference>/cost/", AIRenderCostView.as_view()),
    path("api/v1/admin/ai-renders/<uuid:reference>/image/", AIAdminImageView.as_view()),
    path("api/v1/admin/ai-renders/<uuid:reference>/original/", AIAdminImageView.as_view(original=True)),
    path("api/v1/admin/permissions/", views.PermissionsView.as_view()),
    path("api/v1/admin/uploads/", views.UploadView.as_view()),
    path("api/v1/admin/", include(router.urls)),
    path("api/v1/catalog/", views.public_catalog),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
