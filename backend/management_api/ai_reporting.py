"""Private, bounded generation reporting. Never serialize AIRender wholesale."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .ai_service import PROVIDERS, SuperuserOnly, current_config, provider_profile, decrypt_api_key
from .ai_costs import sync_relay_cost
from .ai_images import image_metadata, image_response, maybe_cleanup_images, with_image_size
from .audit import audit
from .models import AIRender

STATUSES = ('queued', 'generating', 'ready', 'failed', 'cancelled')
LOG_FIELDS = ('id', 'request_key', 'provider', 'model_name', 'style_name', 'phone_model',
              'status', 'created_at', 'started_at', 'completed_at', 'api_started_at',
              'api_finished_at', 'api_duration_ms', 'http_status', 'provider_request_id',
              'request_params', 'usage', 'cost_amount', 'cost_currency', 'cost_source',
              'cost_details', 'cost_recorded_at', 'error_code', 'error_message', 'credit_restored',
              'image_expires_at', 'image_deleted_at', 'image_size_bytes', 'original_size_bytes', 'input_mime')


class ReportFilter(serializers.Serializer):
    start = serializers.DateField(default=lambda: timezone.localdate()-timedelta(days=29))
    end = serializers.DateField(default=timezone.localdate)
    provider = serializers.ChoiceField(choices=('', *PROVIDERS), required=False, default='')
    model = serializers.CharField(max_length=80, required=False, allow_blank=True, default='')
    status = serializers.ChoiceField(choices=('', *STATUSES), required=False, default='')
    search = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    page = serializers.IntegerField(min_value=1, max_value=1_000_000, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=50, default=20)

    def validate(self, data):
        if data['end'] < data['start'] or (data['end']-data['start']).days > 365:
            raise serializers.ValidationError('请选择不超过 366 天的有效日期范围。')
        if data['start'].year < 1900 or data['end'].year > 9998:
            raise serializers.ValidationError('日期超出支持的统计范围。')
        return data


def filtered(request):
    serializer = ReportFilter(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(params['start'], time.min), tz)
    end = timezone.make_aware(datetime.combine(params['end']+timedelta(days=1), time.min), tz)
    qs = AIRender.objects.filter(created_at__gte=start, created_at__lt=end).order_by()
    for name, field in (('provider', 'provider'), ('model', 'model_name'), ('status', 'status')):
        if params[name]:
            qs = qs.filter(**{field: params[name]})
    if params['search']:
        value = params['search']
        match = Q(provider_request_id__icontains=value) | Q(style_name__icontains=value) | Q(phone_model__icontains=value)
        try:
            identifier = UUID(value.removeprefix('AI-'))
            match |= Q(pk=identifier) | Q(request_key=identifier)
        except ValueError:
            pass
        qs = qs.filter(match)
    return qs, params


def amount(value):
    return str(Decimal(value).quantize(Decimal('0.00000001'))) if value is not None else None


def cost_groups(qs, *group_by):
    rows = qs.filter(cost_amount__isnull=False).values(*group_by, 'cost_currency').annotate(
        count=Count('id'), total=Sum('cost_amount'),
        reported=Sum('cost_amount', filter=Q(cost_source='reported')),
        estimated=Sum('cost_amount', filter=Q(cost_source='estimated'))).order_by(*group_by, 'cost_currency')
    return [{**row, **{key: amount(row[key]) for key in ('total', 'reported', 'estimated')}} for row in rows]


def measures():
    return dict(total=Count('id'), ready=Count('id', filter=Q(status='ready')),
        failed=Count('id', filter=Q(status='failed')), cancelled=Count('id', filter=Q(status='cancelled')),
        pending=Count('id', filter=Q(status__in=('queued', 'generating'))),
        recorded_calls=Count('id', filter=Q(api_started_at__isnull=False)),
        priced=Count('id', filter=Q(cost_amount__isnull=False)),
        unpriced=Count('id', filter=Q(status__in=('ready', 'failed'), cost_amount__isnull=True)),
        avg_duration_ms=Avg('api_duration_ms'))


def safe_log(row):
    row['image'] = image_metadata(row)
    row['original'] = image_metadata(row, original=True)
    row['cost_amount'] = amount(row['cost_amount'])
    row['provider_label'] = PROVIDERS.get(row['provider'], {}).get('label', row['provider'])
    row['endpoint'] = PROVIDERS.get(row['provider'], {}).get('base_url', '') + '/images/edits'
    return row


@method_decorator(never_cache, name='dispatch')
class AIUsageView(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request):
        maybe_cleanup_images()
        qs, params = filtered(request)
        summary = qs.aggregate(**measures())
        finished = summary['ready'] + summary['failed']
        summary['success_rate'] = round(summary['ready'] / finished * 100, 1) if finished else None
        summary['costs'] = cost_groups(qs)
        days = qs.annotate(day=TruncDate('created_at'))
        daily = {row['day']: row for row in days.values('day').annotate(**measures()).order_by('day')}
        daily_costs = {}
        for row in cost_groups(days, 'day'):
            daily_costs.setdefault(row.pop('day'), []).append(row)
        trend = []
        for offset in range((params['end']-params['start']).days+1):
            day = params['start']+timedelta(days=offset)
            trend.append({**daily.get(day, {'day': day, 'total': 0, 'ready': 0, 'failed': 0, 'unpriced': 0}), 'costs': daily_costs.get(day, [])})
        model_costs = {}
        for row in cost_groups(qs, 'provider', 'model_name'):
            key = (row.pop('provider'), row.pop('model_name'))
            model_costs.setdefault(key, []).append(row)
        models = list(qs.values('provider', 'model_name').annotate(**measures()).order_by('-total', 'provider', 'model_name'))
        for row in models:
            row['costs'] = model_costs.get((row['provider'], row['model_name']), [])
        return Response({'summary': summary, 'daily': trend, 'models': models,
            'image_retention_days': current_config().image_retention_days,
            'timezone': str(timezone.get_current_timezone()), 'start': params['start'], 'end': params['end'],
            'providers': [{'id': key, 'label': info['label'], 'models': info['models']} for key, info in PROVIDERS.items()]})


@method_decorator(never_cache, name='dispatch')
class AICallLogsView(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request):
        qs, params = filtered(request)
        page = Paginator(with_image_size(qs).values(*LOG_FIELDS).order_by('-created_at', '-id'), params['page_size']).get_page(params['page'])
        return Response({'count': page.paginator.count, 'page': page.number,
                         'results': [safe_log(row) for row in page.object_list]})


@method_decorator(never_cache, name='dispatch')
class AIRenderCostView(APIView):
    permission_classes = [SuperuserOnly]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ai_connection'

    @sensitive_variables()
    def post(self, request, reference):
        job = get_object_or_404(AIRender.objects.defer('input_image', 'result_image', 'prompt'), pk=reference)
        if job.provider != 'ai778' or job.status not in ('ready', 'failed') or not job.provider_request_id:
            raise serializers.ValidationError('此记录没有可补查的七七八任务号。')
        if job.cost_source != 'reported':
            profile = provider_profile(current_config(), 'ai778')
            if not profile.api_key_ciphertext:
                raise serializers.ValidationError('请先在生图配置中保存七七八 API Key。')
            sync_relay_cost(job, decrypt_api_key(profile))
            audit(request, 'update', 'management_api.airender', job, '补查七七八生图费用')
        return Response(safe_log(with_image_size(AIRender.objects.all()).values(*LOG_FIELDS).get(pk=job.pk)))


@method_decorator(never_cache, name='dispatch')
class AIAdminImageView(APIView):
    permission_classes = [SuperuserOnly]
    original = False

    def get(self, request, reference):
        qs = AIRender.objects.only('input_image' if self.original else 'result_image', 'input_mime',
                                   'image_expires_at', 'image_deleted_at')
        if not self.original:
            qs = qs.filter(status='ready')
        job = get_object_or_404(qs, pk=reference)
        return image_response(job, download=request.query_params.get('download') == '1', original=self.original,
                              thumbnail=request.query_params.get('thumbnail') == '1')
