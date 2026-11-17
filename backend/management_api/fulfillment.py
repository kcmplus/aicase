"""Delivery eligibility, independent of payment and supplier queue state."""
from .models import PrintOrder
from django.conf import settings

SHIPPING_UNAVAILABLE = 'This delivery method is not available for checkout. Choose nearby printing or courier delivery.'


def require_pickup(order):
    from .orders import Conflict
    if order.fulfillment_type != PrintOrder.Fulfillment.PICKUP:
        raise Conflict('Confirm on-site pickup before using a print station. Delivery orders cannot be sent to a station.')


def require_checkout(order):
    from .orders import Conflict
    if getattr(order, 'refund', None) and order.refund.status != 'failed':
        raise Conflict('This order has a refund in progress. Payment is not available.')
    if order.fulfillment_type == PrintOrder.Fulfillment.COURIER:
        from .courier import frozen_courier_valid
        if not frozen_courier_valid(order):
            raise Conflict('This delivery order needs its address and frozen quote reviewed before payment.')
        return
    if order.fulfillment_type == PrintOrder.Fulfillment.AIR:
        raise Conflict(SHIPPING_UNAVAILABLE)
    require_pickup(order)


def cloud_release_available():
    # New cloud-only switch. The old terminal/IPC switch remains retired.
    return settings.SUPPLIER_ORDER_ENABLED and settings.SUPPLIER_PAYMENT_ENABLED
