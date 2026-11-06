"""One active channel for new orders; existing orders retain their channel."""
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AirwallexConfig, StripeConfig, PrintOrder
from .orders import StoreOrders, owner, Conflict
from .audit import audit


def lock_configs():
    # All config writes acquire these locks in the same order.
    stripe, _ = StripeConfig.objects.select_for_update().get_or_create(pk=1)
    airwallex, _ = AirwallexConfig.objects.select_for_update().get_or_create(pk=1)
    return stripe, airwallex


def disable_other(request, config):
    if config.enabled:
        config.enabled = False
        config.revision += 1
        config.save(update_fields=['enabled', 'revision', 'updated_at'])
        audit(request, 'update', config._meta.label_lower, config, '切换支付渠道，停止此渠道接收新订单')


def payment_config():
    from . import stripe_payments, airwallex_payments
    config = airwallex_payments.current_config()
    if config.enabled:
        return airwallex_payments.payment_config(config)
    return stripe_payments.payment_config()


def checkout_settings(provider, mode):
    from . import stripe_payments, airwallex_payments
    public = payment_config()
    if provider != public['provider'] or mode != public['mode']:
        raise Conflict('Payment settings changed. Reload to review the payment method.')
    if provider == 'airwallex':
        return airwallex_payments.checkout_settings(mode)
    return stripe_payments.checkout_settings(provider, mode)


@method_decorator(never_cache, name='dispatch')
class PublicPaymentConfig(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(payment_config())


class PaymentCheckout(StoreOrders):
    http_method_names = ['post', 'options']

    def post(self, request, reference):
        from .stripe_payments import StripeCheckout
        from .airwallex_payments import AirwallexCheckout
        order = get_object_or_404(PrintOrder, reference=reference, owner_hash=owner(request))
        from .fulfillment import require_checkout
        require_checkout(order)
        from .models import SupplierOrder
        if SupplierOrder.objects.filter(order=order, state='draft').exists():
            raise Conflict('Upload the final print files before continuing to payment.')
        view = AirwallexCheckout if order.mode.startswith('airwallex_') else StripeCheckout
        return view().post(request, reference)
