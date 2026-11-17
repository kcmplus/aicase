"""Fixed courier quotes; intentionally independent of station inventory and dispatch."""
from decimal import Decimal, InvalidOperation
from rest_framework import serializers
from .models import PricingPlan


class DeliveryAddress(serializers.Serializer):
    recipient = serializers.CharField(max_length=60)
    phone = serializers.CharField(min_length=6, max_length=24)
    region = serializers.CharField(max_length=150)
    street = serializers.CharField(max_length=250)
    postal = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError('Unsupported delivery address fields.')
        return super().to_internal_value(data)


def courier_quote(print_plan=None, lock=False):
    from .orders import Conflict
    plans = PricingPlan.objects.select_for_update() if lock else PricingPlan.objects
    print_plan = print_plan or plans.filter(kind='print', active=True).first()
    shipping = plans.filter(kind='courier_shipping', active=True).first()
    if not print_plan or not shipping:
        raise Conflict('Courier pricing is unavailable. Please reload or choose nearby printing.')
    if shipping.currency != print_plan.currency or shipping.currency != 'USD':
        raise Conflict('Courier pricing currency needs review.')
    if print_plan.price < 0 or shipping.price < 0:
        raise Conflict('Courier pricing needs review.')
    total = print_plan.price + shipping.price
    if (total != 0 and total < Decimal('0.50')) or total > Decimal('999999.99'):
        raise Conflict('Courier checkout total must be zero or between USD 0.50 and USD 999999.99.')
    return {'version': 1, 'print_amount': str(print_plan.price), 'shipping_amount': str(shipping.price),
            'total_amount': str(total), 'currency': shipping.currency}


def frozen_courier_valid(order):
    """Historical delivery orders without a reviewed quote must never become payable."""
    q = order.shipping_quote
    if not isinstance(q, dict) or q.get('version') != 1 or q.get('currency') != order.currency:
        return False
    try:
        base, fee, total = (Decimal(q[key]) for key in ('print_amount', 'shipping_amount', 'total_amount'))
        return (all(v.is_finite() and v >= 0 for v in (base, fee, total))
                and base + fee == total == order.amount and (total == 0 or total >= Decimal('0.50'))
                and DeliveryAddress(data=order.delivery_address).is_valid())
    except (InvalidOperation, ValueError, TypeError, KeyError):
        return False
