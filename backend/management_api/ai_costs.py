"""Allowlisted call telemetry and versioned Images API cost estimates.

Never retain raw responses, images, prompts or credentials in telemetry.
Missing usage is unknown, including for failed requests; it is never free.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .models import AIRender

# Standard direct Images API rates, checked 2026-10-30. Cached input discounts
# for Image 2/2.5 apply only to Responses, not our /v1/images/edits endpoint.
# https://developers.openai.com/api/docs/guides/image-generation#cost-and-latency
# https://developers.openai.com/api/docs/models/gpt-image-1-mini
# https://developers.openai.com/api/docs/models/gpt-image-1.5
# https://developers.openai.com/api/docs/models/chatgpt-image-latest
RATES = {
    'gpt-image-2': ('5', '8', '30', None),
    'gpt-image-2.5-flare': ('5', '8', '30', None),
    'gpt-image-2.5-sunburst': ('5', '8', '30', None),
    'gpt-image-1-mini': ('2', '2.5', '8', None),
    'gpt-image-1.5': ('5', '8', '32', '10'),
    'chatgpt-image-latest': ('5', '8', '32', '10'),
}
PRECISION = Decimal('0.00000001')


def safe_usage(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in ('input_tokens', 'output_tokens', 'total_tokens'):
        number = value.get(key)
        if type(number) is int and 0 <= number <= 1_000_000_000:
            result[key] = number
    for key in ('input_tokens_details', 'output_tokens_details'):
        if isinstance(value.get(key), dict):
            result[key] = {name: number for name, number in value[key].items()
                           if name in ('text_tokens', 'image_tokens', 'cached_tokens')
                           and type(number) is int and 0 <= number <= 1_000_000_000}
    return result


def safe_request_id(value, api_key=''):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_.:-]{1,150}', value):
        return ''
    return '' if (api_key and api_key in value) or value.startswith(('sk-', 'Bearer')) else value


def price_snapshot(provider, model):
    if provider != 'openai' or model not in RATES:
        return {}
    return {'version': '2026-10-30', 'currency': 'USD', 'basis': 'standard_images_api',
            'source_url': 'https://developers.openai.com/api/docs/models/' + model,
            'rates_per_million': dict(zip(('input_text', 'input_image', 'output_image', 'output_text'), RATES[model]))}


def estimate_cost(usage, snapshot):
    """Require complete modality counts. Never infer missing input usage as zero."""
    if not snapshot:
        return None, 'price_unavailable', {}
    if not usage:
        return None, 'usage_missing', {}
    inputs = usage.get('input_tokens_details', {})
    if not all(key in inputs for key in ('text_tokens', 'image_tokens')) or 'output_tokens' not in usage:
        return None, 'usage_incomplete', {}
    text, image = inputs['text_tokens'], inputs['image_tokens']
    if 'input_tokens' in usage and usage['input_tokens'] != text + image:
        return None, 'usage_inconsistent', {}
    output = usage['output_tokens']
    if 'total_tokens' in usage and usage['total_tokens'] != text + image + output:
        return None, 'usage_inconsistent', {}
    details = usage.get('output_tokens_details')
    if details is None:
        out_image, out_text = output, 0
    elif all(key in details for key in ('image_tokens', 'text_tokens')) and sum(details[key] for key in ('image_tokens', 'text_tokens')) == output:
        out_image, out_text = details['image_tokens'], details['text_tokens']
    else:
        return None, 'usage_incomplete', {}
    amounts = {}
    for key, count in (('input_text', text), ('input_image', image), ('output_image', out_image), ('output_text', out_text)):
        rate = snapshot['rates_per_million'][key]
        if count and rate is None:
            return None, 'price_unavailable', {}
        amounts[key] = Decimal(count) * Decimal(rate or '0') / 1_000_000
    total = sum(amounts.values()).quantize(PRECISION, rounding=ROUND_HALF_UP)
    return total, 'usage_estimate', {key: str(value.quantize(PRECISION)) for key, value in amounts.items()}


class CallTelemetry:
    def __init__(self, job, params):
        self.job = job
        self.started = time.monotonic()
        self.usage = {}
        self.request_id = ''
        self.http_status = None
        self.snapshot = price_snapshot(job.provider, job.model_name)
        AIRender.objects.filter(pk=job.pk).update(api_started_at=timezone.now(),
            request_params=params, cost_details={'pricing': self.snapshot, 'reason': 'pending'})

    def response(self, status, request_id, data=None):
        self.http_status = status if type(status) is int and 100 <= status <= 599 else None
        self.request_id = request_id
        if isinstance(data, dict):
            self.usage = safe_usage(data.get('usage'))

    def finish(self):
        amount, reason, breakdown = estimate_cost(self.usage, self.snapshot)
        if self.job.provider == 'ai778':
            reason = 'awaiting_relay_cost' if self.request_id else 'relay_task_missing'
        AIRender.objects.filter(pk=self.job.pk).update(api_finished_at=timezone.now(),
            api_duration_ms=min(2_147_483_647, max(0, round((time.monotonic()-self.started)*1000))),
            http_status=self.http_status, provider_request_id=self.request_id, usage=self.usage,
            cost_amount=amount, cost_currency='USD' if amount is not None else '',
            cost_source='estimated' if amount is not None else 'unknown',
            cost_details={'reason': reason, 'pricing': self.snapshot, 'breakdown': breakdown},
            cost_recorded_at=timezone.now() if amount is not None else None)


def decimal_cost(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)) or len(str(value)) > 40:
        return None
    try:
        number = Decimal(str(value))
        if number.is_finite() and 0 <= number <= Decimal('999999999'):
            return number.quantize(PRECISION, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        pass
    return None


@sensitive_variables()
def sync_relay_cost(job, api_key):
    """Read the final net debit, in platform compute credits (NOT CNY or USD).

    https://ai778.cc/apidoc#common/task_status
    https://ai778.cc/apidoc#common/balance
    This happens after publishing the image. A failed lookup never fails a render.
    """
    from .ai_service import PROVIDERS, NoRedirect
    if job.provider != 'ai778' or job.cost_source == 'reported' or not re.fullmatch(r'[0-9]{1,30}', job.provider_request_id):
        return
    reason = 'relay_lookup_failed'
    try:
        url = PROVIDERS['ai778']['base_url']+'/skills/task-status?'+urllib.parse.urlencode({'task_id': job.provider_request_id})
        request = urllib.request.Request(url, headers={'Authorization': 'Bearer '+api_key, 'Accept': 'application/json'})
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=5) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError()
        data = json.loads(payload)
        if not isinstance(data, dict) or str(data.get('task_id')) != job.provider_request_id:
            raise ValueError()
        cost = decimal_cost(data.get('cost'))
        if data.get('is_final') is True and data.get('state') in ('success', 'failed') and cost is not None:
            usage = {**job.usage, **safe_usage(data)}
            if 'total_tokens' not in usage and all(key in usage for key in ('input_tokens', 'output_tokens')):
                usage['total_tokens'] = usage['input_tokens']+usage['output_tokens']
            AIRender.objects.filter(pk=job.pk, cost_source='unknown').update(cost_amount=cost,
                cost_currency='AI778', cost_source='reported', cost_recorded_at=timezone.now(), usage=usage,
                cost_details={'reason': 'relay_reported', 'state': data['state'],
                              'source_url': 'https://ai778.cc/apidoc#common/task_status'})
            return
        if data.get('is_final') is not True:
            reason = 'relay_pending'
    except urllib.error.HTTPError as error:
        error.close()
    except Exception:
        # Metadata is best effort. Never expose upstream error bodies or credentials.
        pass
    AIRender.objects.filter(pk=job.pk, cost_source='unknown').update(cost_details={**job.cost_details, 'reason': reason})
