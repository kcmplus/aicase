"""Browser-owned case orders; station actions remain explicitly simulated."""
import base64
import hashlib
import json
import re
import warnings
from io import BytesIO
from pathlib import Path
from django.db.models import Q
from .phone_templates import template_for, PHONE_TEMPLATES
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from PIL import Image
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from .models import PrintOrder, PhoneModel, DesignTemplate, PricingPlan, Graphic, AuditLog
from .customer_auth import customer_for

# The renderer is versioned with the storefront. Validate against its fixed layer IDs,
# rather than mutable admin layouts that the storefront does not yet consume.
LAYERS = {item['id']: {layer['id'] for layer in item['layout']['layers']} for item in json.loads((Path(__file__).parent / 'seed/catalog.json').read_text())['designs']}

class Conflict(APIException):
    status_code = 409
    default_detail = 'This order changed. Refresh it before trying again.'

class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError({'detail': 'Unsupported order fields.'})
        return super().to_internal_value(data)

class Placement(StrictSerializer):
    x = serializers.FloatField(min_value=0, max_value=100)
    y = serializers.FloatField(min_value=0, max_value=100)
    scale = serializers.FloatField(min_value=25, max_value=200)
    rotation = serializers.FloatField(min_value=-180, max_value=180)
    def validate(self, data):
        import math
        if not all(math.isfinite(data[key]) for key in ('x', 'y', 'scale', 'rotation')):
            raise serializers.ValidationError('Invalid artwork position.')
        return data

class Artwork(Placement):
    id = serializers.RegexField(r'^extra-[a-zA-Z0-9-]{1,60}$')
    type = serializers.ChoiceField(choices=['text', 'sticker'])
    text = serializers.CharField(max_length=80, allow_blank=True, required=False, trim_whitespace=False)
    font = serializers.ChoiceField(choices=['sans','serif','mono','hand'], required=False)
    color = serializers.RegexField(r'^#[0-9a-fA-F]{6}$', required=False)
    asset = serializers.SlugField(max_length=80, required=False)
    def validate(self, data):
        super().validate(data)
        if data['type'] == 'text' and not all(k in data for k in ('text','font','color')):
            raise serializers.ValidationError('Incomplete text style.')
        if data['type'] == 'sticker' and not Graphic.objects.filter(code=data.get('asset'), active=True).exists():
            raise serializers.ValidationError('This graphic is unavailable.')
        return data

class LayerEdit(Placement):
    deleted = serializers.BooleanField(required=False)
    text = serializers.CharField(max_length=80, allow_blank=True, required=False, trim_whitespace=False)
    font = serializers.ChoiceField(choices=['sans','serif','mono','hand'], required=False)
    color = serializers.RegexField(r'^#[0-9a-fA-F]{6}$', required=False)
    def validate(self, data):
        super().validate(data)
        if 'text' in data and not all(k in data for k in ('font','color')):
            raise serializers.ValidationError('Incomplete text style.')
        return data

class Layout(StrictSerializer):
    zoom = serializers.FloatField(min_value=50, max_value=180)
    x = serializers.FloatField(min_value=0, max_value=100)
    y = serializers.FloatField(min_value=0, max_value=100)
    artworkEdits = serializers.DictField(child=LayerEdit(), default=dict)

class AIMetadata(StrictSerializer):
    styleId = serializers.SlugField(max_length=80)
    jobId = serializers.CharField(max_length=50, allow_blank=True)
    mode = serializers.ChoiceField(choices=['demo','live'])

class Snapshot(Layout):
    version = serializers.IntegerField(min_value=2, max_value=2)
    code = serializers.RegexField(r'^POP-C-[A-F0-9]{16}$')
    source = serializers.ChoiceField(choices=['collection','photo'])
    designId = serializers.SlugField(max_length=80)
    model = serializers.CharField(max_length=120)
    phoneTemplateId = serializers.SlugField(max_length=80, required=False)
    photo = serializers.CharField(max_length=3_000_000, allow_blank=True, default='')
    effect = serializers.ChoiceField(choices=['original','fresh','warm','bold'])
    intensity = serializers.FloatField(min_value=0, max_value=100)
    addedArtwork = Artwork(many=True, required=False, max_length=20)
    photoPlacement = Placement(required=False)
    collectionLayout = Layout(required=False)
    ai = AIMetadata(required=False)
    def validate(self, data):
        # JSON must be finite even for values where a serializer range comparison
        # alone would permit NaN. Clients cannot submit HTML, SVG or remote URLs.
        try:
            json.dumps(data, allow_nan=False)
        except ValueError:
            raise serializers.ValidationError('Invalid design numbers.')
        if not PhoneModel.objects.filter(
            Q(legacy_index__isnull=False) | Q(code__in=[t['code'] for t in PHONE_TEMPLATES]),
            name=data['model'], active=True, brand__active=True,
        ).exists():
            raise serializers.ValidationError('This phone model is unavailable.')
        if 'phoneTemplateId' in data and not template_for(data['model'], data['phoneTemplateId']):
            raise serializers.ValidationError('This phone template is unavailable.')
        template = template_for(data['model'])
        if template:
            data.setdefault('phoneTemplateId', template['id'])
        if data['designId'] not in LAYERS or not DesignTemplate.objects.filter(code=data['designId'], active=True).exists():
            raise serializers.ValidationError('This design is unavailable.')
        for layout in (data, data.get('collectionLayout', {})):
            if set(layout.get('artworkEdits', {})) - LAYERS[data['designId']]:
                raise serializers.ValidationError('Invalid template layer.')
        ids = [a['id'] for a in data.get('addedArtwork', [])]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError('Duplicate artwork.')
        if data['source'] == 'photo':
            if data['zoom'] < 100:
                raise serializers.ValidationError('Invalid photo crop.')
            match = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/]+=*)', data['photo'])
            try:
                if not match:
                    raise ValueError()
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(BytesIO(base64.b64decode(match[2], validate=True))) as img:
                        if img.format.lower().replace('jpg','jpeg') != match[1] or img.width * img.height > 4_000_000:
                            raise ValueError()
                        img.verify()
            except Exception:
                raise serializers.ValidationError('Upload a valid JPG, PNG or WebP photo (up to 4 megapixels).')
        elif data['photo']:
            raise serializers.ValidationError('Unexpected photo in a collection design.')
        return data

class Checkout(StrictSerializer):
    payment_mode = serializers.ChoiceField(choices=['demo', 'test', 'live'], default='demo')
    payment_provider = serializers.ChoiceField(choices=['demo', 'stripe', 'airwallex'], default='demo')
    request_key = serializers.UUIDField()
    accepted = serializers.BooleanField()
    expected_amount = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0'))
    customer_email = serializers.EmailField(allow_blank=True, required=False, default='')
    # An expected session identity, not a customer ID that clients may assign.
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    snapshot = Snapshot()
    def validate_accepted(self, value):
        if not value:
            raise serializers.ValidationError('Confirm your design and payment first.')
        return value

class Revision(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)
    accepted = serializers.BooleanField()
    snapshot = Snapshot()
    def validate_accepted(self, value):
        if not value:
            raise serializers.ValidationError('Confirm the updated design first.')
        return value

class Action(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=['start','ready','collect','cancel'])
    station_id = serializers.ChoiceField(choices=['DEMO-01','DEMO-02','DEMO-03'], required=False)
    code = serializers.CharField(max_length=30)


def owner(request):
    token = request.headers.get('X-Order-Key', '')
    if not re.fullmatch(r'[0-9a-f]{64}', token):
        raise PermissionDenied('This browser needs its order access key. Please reload.')
    return hashlib.sha256(token.encode()).hexdigest()


def order_data(order, detail=True):
    result = {key: getattr(order, key) for key in ('reference','model_name','customer_email','status','amount','currency','mode','revision','station_id','created_at','updated_at')}
    from .refunds import refund_data
    result['refund'] = refund_data(order)
    result['code'] = order.snapshot.get('code', '')
    if detail:
        result['snapshot'] = order.snapshot
    return result


def log(order, action):
    label = {'create':'确认订单','revise':'修改设计','start':'开始打印','ready':'打印完成，待取货','collect':'确认取货','cancel':'取消订单'}[action]
    AuditLog.objects.create(actor_name='顾客', action=action, resource='management_api.printorder', object_id=str(order.pk), summary=f'{order.mode} 订单 {order.reference} · {label}')

@method_decorator(never_cache, name='dispatch')
class StoreOrders(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []  # Browser key owns orders; customer session only supplies checkout identity.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'orders'
    def get(self, request):
        qs = PrintOrder.objects.filter(owner_hash=owner(request)).defer('snapshot').order_by('-created_at')
        try:
            page = max(1, min(10000, int(request.query_params.get('page', '1'))))
        except ValueError:
            raise serializers.ValidationError('Invalid page.')
        rows = list(qs[(page-1)*20:page*20+1])
        # List responses exclude private photos and design codes.
        data = [{key: getattr(o, key) for key in ('reference','model_name','status','amount','currency','mode','created_at')} for o in rows[:20]]
        return Response({'results':data, 'has_more':len(rows)>20, 'page':page})
    @transaction.atomic
    def post(self, request):
        owner_hash = owner(request)
        customer = customer_for(request)
        if customer:
            SessionAuthentication().enforce_csrf(request)
        # Serialize checkout/retry against the same pricing record. PostgreSQL's
        # unique request_key also guards simultaneous requests across workers.
        plan = PricingPlan.objects.select_for_update().filter(kind='print', active=True).first()
        if not isinstance(request.data, dict):
            raise serializers.ValidationError({'detail':'Expected an order object.'})
        request_key = serializers.UUIDField().run_validation(request.data.get('request_key'))
        existing = PrintOrder.objects.filter(request_key=request_key).first()
        if existing:
            if existing.owner_hash != owner_hash:
                raise Conflict('This checkout key has already been used.')
            if existing.status == 'pending' and existing.mode.startswith(('stripe_', 'airwallex_')):
                expected_provider = existing.mode.rsplit('_', 1)[0]
                expected_mode = expected_provider + '_' + str(request.data.get('payment_mode', ''))
                if request.data.get('payment_provider') != expected_provider or expected_mode != existing.mode:
                    raise Conflict('This order uses a different payment environment. Open it from My orders to review it.')
            # Later edits must not make a retry overwrite the order snapshot.
            return Response(order_data(existing))
        payload = {**request.data, 'customer_email': customer.email} if customer else request.data
        serializer = Checkout(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'customer_id' in data and data['customer_id'] != (customer.pk if customer else None):
            raise Conflict('Your sign-in changed. Reload checkout to review your email.')
        if not plan:
            raise Conflict('Printing is unavailable. Please try again later.')
        if data['expected_amount'] != plan.price:
            raise Conflict(f'The print price changed to {plan.currency} {plan.price}. Reload to review the new price.')
        from .payments import checkout_settings
        payment = checkout_settings(data['payment_provider'], data['payment_mode'])
        if payment['mode'].startswith(('stripe_', 'airwallex_')) and plan.price < Decimal('0.50'):
            raise Conflict('Online payment requires a print price of at least USD 0.50.')
        order = PrintOrder.objects.create(owner_hash=owner_hash, request_key=data['request_key'], **payment, model_name=data['snapshot']['model'], amount=plan.price, currency=plan.currency, customer=customer, customer_email=data['customer_email'], snapshot=data['snapshot'])
        log(order, 'create')
        return Response(order_data(order), status=201)

@method_decorator(never_cache, name='dispatch')
class StoreOrder(StoreOrders):
    def get(self, request, reference):
        return Response(order_data(get_object_or_404(PrintOrder, reference=reference, owner_hash=owner(request))))
    @transaction.atomic
    def patch(self, request, reference):
        order = get_object_or_404(PrintOrder.objects.select_for_update(), reference=reference, owner_hash=owner(request))
        serializer = Revision(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if order.mode != 'demo' or order.status != 'paid':
            raise Conflict('This order can no longer be edited. Create a new order.')
        if data['snapshot'] == order.snapshot and data['revision'] + 1 == order.revision:
            return Response(order_data(order))
        if data['revision'] != order.revision:
            raise Conflict()
        if data['snapshot']['code'] == order.snapshot.get('code'):
            raise Conflict('Save changes with a new design code.')
        order.snapshot = data['snapshot']
        order.model_name = data['snapshot']['model']
        order.revision += 1
        order.save(update_fields=['snapshot','model_name','revision','updated_at'])
        log(order, 'revise')
        return Response(order_data(order))
    def post(self, request, reference):
        return Response(status=405)

class StoreOrderAction(StoreOrder):
    http_method_names = ['post','options']
    @transaction.atomic
    def post(self, request, reference):
        order = get_object_or_404(PrintOrder.objects.select_for_update(), reference=reference, owner_hash=owner(request))
        serializer = Action(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        previous, target = {'start':('paid','printing'), 'ready':('printing','ready'), 'collect':('ready','completed'), 'cancel':('paid','cancelled')}[data['action']]
        if order.mode != 'demo' or data['code'] != order.snapshot.get('code'):
            raise Conflict('Use the latest design code for this test order.')
        if order.status == target and order.revision == data['revision'] + 1:
            return Response(order_data(order))
        if order.status != previous or order.revision != data['revision']:
            raise Conflict('Order status changed. Refresh before continuing.')
        if data['action'] == 'start':
            station = data.get('station_id')
            if station not in ('DEMO-01','DEMO-02') or (station == 'DEMO-02' and order.model_name not in ('iPhone 16 Pro','iPhone 16')):
                raise serializers.ValidationError('This demo station is offline or does not have the selected case.')
            order.station_id = station
        order.status = target
        order.revision += 1
        order.save(update_fields=['status','station_id','revision','updated_at'])
        log(order, data['action'])
        return Response(order_data(order))
