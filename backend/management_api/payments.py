"""One active channel for new orders; existing orders retain their channel."""
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AirwallexConfig, StripeConfig, PrintOrder, PricingPlan
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


def payment_config(fulfillment_type="pickup"):
    from . import stripe_payments, airwallex_payments
    # A zero-priced print plan is an explicit no-charge workflow test, never a live receipt.
    if fulfillment_type == 'pickup' and PricingPlan.objects.filter(kind='print', active=True, price=0).exists():
        return {'provider': 'free', 'mode': 'test', 'available': True, 'zero_price_test': True}
    if fulfillment_type == 'courier':
        from .courier import courier_quote
        if courier_quote()['total_amount'] == '0.00':
            return {'provider': 'free', 'mode': 'test', 'available': True, 'zero_price_test': True}
    config = airwallex_payments.current_config()
    if config.enabled:
        return airwallex_payments.payment_config(config)
    return stripe_payments.payment_config()


def checkout_settings(provider, mode, fulfillment_type="pickup"):
    from . import stripe_payments, airwallex_payments
    public = payment_config(fulfillment_type)
    if fulfillment_type == "courier" and not public.get("zero_price_test") and (provider not in ("stripe", "airwallex") or not public["available"]):
        raise Conflict("Configure an online payment channel before accepting courier orders.")
    if settings.DIRECT_DEBUG_ENABLED and (fulfillment_type == 'courier' or not public.get('zero_price_test')):
        raise Conflict('Direct simulation only supports the zero-price test plan.')
    if provider != public['provider'] or mode != public['mode']:
        raise Conflict('Payment settings changed. Reload to review the payment method.')
    if public.get('zero_price_test'):
        return {'mode': 'free_test', 'status': 'paid', 'paid_at': timezone.now()}
    if provider == 'airwallex':
        return airwallex_payments.checkout_settings(mode)
    return stripe_payments.checkout_settings(provider, mode)


@method_decorator(never_cache, name='dispatch')
class PublicPaymentConfig(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        method = request.query_params.get('fulfillment_type', 'pickup')
        if method not in ('pickup', 'courier'):
            raise Conflict('Choose nearby printing or courier delivery.')
        config = payment_config(method)
        if method == 'courier':
            from .courier import courier_quote
            config = {**config, 'fulfillment_type': 'courier', 'quote': courier_quote()}
            config['available'] = config['available'] and (config.get('zero_price_test') or config['provider'] in ('stripe', 'airwallex')) and not settings.DIRECT_DEBUG_ENABLED
        return Response(config)


class PaymentCheckout(StoreOrders):
    http_method_names = ['post', 'options']

    def post(self, request, reference):
        if settings.DIRECT_DEBUG_ENABLED:
            raise Conflict('Online checkout is disabled in direct simulation.')
        from .stripe_payments import StripeCheckout
        from .airwallex_payments import AirwallexCheckout
        order = get_object_or_404(PrintOrder, reference=reference, owner_hash=owner(request))
        from .fulfillment import require_checkout
        require_checkout(order)
        if order.mode == 'free_test':
            raise Conflict('No payment is required for this order.')
        from .models import SupplierOrder
        if SupplierOrder.objects.filter(order=order, state='draft').exists():
            raise Conflict('Upload the final print files before continuing to payment.')
        view = AirwallexCheckout if order.mode.startswith('airwallex_') else StripeCheckout
        return view().post(request, reference)
