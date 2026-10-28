"""Private, durable image-edit jobs using the administrator's configured key.

The detached worker claims each job exactly once. An ambiguous network failure
is never retried automatically; a new request requires another user action.
"""
import base64
import calendar
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import warnings
from datetime import datetime, timedelta, timezone as datetime_timezone
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables, sensitive_post_parameters
from PIL import Image, ImageOps
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .ai_service import API_BASE, NoRedirect, current_config, decrypt_api_key, encryption_ready
from .models import AIAccount, AIRender, AIServiceConfig, AIStyle, PhoneModel, PricingPlan
from .orders import owner, StrictSerializer
from .phone_templates import template_for


class GenerationUnavailable(APIException):
    status_code = 503
    default_detail = 'AI generation is temporarily unavailable. Please try again later.'


class GenerationError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def generation_available():
    return bool(current_config().api_key_ciphertext) and encryption_ready()


def ai_plan():
    plans = list(PricingPlan.objects.filter(kind='ai_monthly', active=True))
    if len(plans) != 1:
        raise GenerationUnavailable('The AI plan is currently unavailable.')
    return plans[0]


def period_boundary(anchor, months):
    start = datetime.fromtimestamp(anchor/1000, tz=datetime_timezone.utc)
    month_index = start.year*12 + start.month-1 + months
    year, month = divmod(month_index, 12)
    day = min(start.day, calendar.monthrange(year, month+1)[1])
    return int(start.replace(year=year, month=month+1, day=day).timestamp()*1000)


def refresh_account(account, plan):
    s = account.subscription
    now = int(timezone.now().timestamp()*1000)
    if s and s.get('renew') and now >= s['endsAt']:
        cycle = s['cycle']+1
        while now >= period_boundary(s['anchor'], cycle+1):
            cycle += 1
        account.subscription = {**s, 'cycle': cycle, 'startsAt': period_boundary(s['anchor'], cycle),
                                'endsAt': period_boundary(s['anchor'], cycle+1), 'used': 0,
                                'monthlyLimit': plan.monthly_credits, 'priceCents': int(plan.price*100)}
        account.save(update_fields=['subscription', 'updated_at'])
    return account


def account_data(account):
    return {'server': True, 'trialCount': account.trial_used, 'trialUsed': account.trial_used > 0,
            'subscription': account.subscription, 'billingMode': 'demo',
            'demoSubscriptionsAvailable': settings.DEBUG}


def render_data(job):
    return {'id': str(job.id), 'requestKey': str(job.request_key), 'mode': 'live', 'status': job.status,
            'styleId': job.style_code, 'styleName': job.style_name, 'model': job.phone_model,
            'phoneTemplateId': job.phone_template_id, 'allocation': job.allocation,
            'createdAt': int(job.created_at.timestamp()*1000),
            'startedAt': int(job.started_at.timestamp()*1000) if job.started_at else None,
            'completedAt': int(job.completed_at.timestamp()*1000) if job.completed_at else None,
            'payment': 'credit_restored' if job.credit_restored else 'credit_reserved',
            'errorCode': job.error_code, 'errorMessage': job.error_message,
            'result': f'/api/v1/store/ai-renders/{job.id}/image/' if job.status == 'ready' else None}


def decode_photo(photo):
    match = re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/]+=*)', photo)
    try:
        if not match:
            raise ValueError()
        raw = base64.b64decode(match[2], validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format.lower().replace('jpg','jpeg') != match[1] or image.width*image.height > 4_000_000:
                    raise ValueError()
                image.verify()
        return raw, 'image/'+match[1]
    except Exception:
        raise serializers.ValidationError('Upload a valid JPG, PNG or WebP photo (up to 4 megapixels).') from None


class RenderInput(StrictSerializer):
    request_key = serializers.UUIDField()
    accepted = serializers.BooleanField()
    photo = serializers.CharField(max_length=3_000_000, trim_whitespace=False)
    style_id = serializers.SlugField(max_length=80)
    model = serializers.CharField(max_length=120)

    def validate_accepted(self, value):
        if not value:
            raise serializers.ValidationError('Confirm using one AI generation first.')
        return value


def build_prompt(style, model, template):
    return ('Edit the supplied image into original phone-case artwork. Preserve the identity, '
            'recognizable features and main subject of the uploaded photo. Apply the following style '
            'to this uploaded subject; do not substitute a stock example or invent a different person.\n\n'
            'STYLE\n'+style.prompt+'\n\nCOMPOSITION\n'+model.adaptation_prompt+
            f'\nThe final case canvas ratio is {template["printWidth"]}:{template["printHeight"]}. '
            'Create a full-bleed portrait artwork that can be cropped to that narrower ratio. '
            'Keep the main subject within the central half of the image and important facial details '
            'below the upper quarter. Extend the background to the edges. The application will apply '
            'the case mask after generation. Do not depict a phone, case border, camera lens, camera '
            'cutout, mockup, watermark or extra text unless the requested style explicitly requires text.')


def restore_credit(job, status, code='', message=''):
    with transaction.atomic():
        AIServiceConfig.objects.filter(pk=1).update(revision=F('revision'))
        locked = AIRender.objects.select_for_update().get(pk=job.pk)
        if locked.status not in ('queued','generating'):
            return locked
        account = AIAccount.objects.select_for_update().get(pk=locked.owner_hash)
        if not locked.credit_restored:
            allocation = locked.allocation
            if allocation.get('type') == 'trial':
                account.trial_used = max(0, account.trial_used-1)
            elif account.subscription and account.subscription['startsAt'] == allocation.get('period'):
                account.subscription = {**account.subscription, 'used': max(0,account.subscription['used']-1)}
            account.save(update_fields=['trial_used','subscription','updated_at'])
        locked.status=status; locked.error_code=code; locked.error_message=message
        locked.credit_restored=True; locked.completed_at=timezone.now(); locked.input_image=b''
        locked.save(update_fields=['status','error_code','error_message','credit_restored','completed_at','input_image','updated_at'])
        return locked


def expire_stale_jobs(owner_hash=None):
    jobs = AIRender.objects.filter(status__in=['queued','generating'], created_at__lt=timezone.now()-timedelta(minutes=10)).defer('input_image','result_image')
    if owner_hash: jobs = jobs.filter(owner_hash=owner_hash)
    for job in jobs:
        restore_credit(job, 'failed', 'interrupted', 'The render was interrupted. Your generation has been returned. Please retry.')


def dispatch_render(job_id):
    try:
        subprocess.Popen([sys.executable, str(settings.BASE_DIR/'manage.py'), 'run_ai_render', str(job_id)],
                         cwd=settings.BASE_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        restore_credit(AIRender.objects.get(pk=job_id), 'failed', 'worker_unavailable', 'The render could not start. Your generation has been returned.')


@method_decorator(never_cache, name='dispatch')
class AIPrivateView(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    throttle_classes=[ScopedRateThrottle]
    throttle_scope='ai_render'


class AIAccountView(AIPrivateView):
    def get(self, request):
        key=owner(request); expire_stale_jobs(key)
        account,_=AIAccount.objects.get_or_create(owner_hash=key)
        return Response(account_data(refresh_account(account, ai_plan())))

    @transaction.atomic
    def post(self, request):
        key=owner(request)
        if not settings.DEBUG:
            raise PermissionDenied('Paid subscriptions are not connected yet.')
        if set(request.data) != {'action','accepted'} or request.data.get('accepted') is not True:
            raise serializers.ValidationError('Confirm the demo subscription change first.')
        action=request.data['action']
        if action not in ('subscribe','stop-renewal','resume-renewal'):
            raise serializers.ValidationError('Unknown subscription action.')
        AIServiceConfig.objects.filter(pk=1).update(revision=F('revision'))
        account,_=AIAccount.objects.select_for_update().get_or_create(owner_hash=key)
        plan=ai_plan();refresh_account(account,plan);s=account.subscription;now=int(timezone.now().timestamp()*1000)
        if action=='stop-renewal':
            if s: account.subscription={**s,'renew':False}
        elif s and now<s['endsAt']:
            account.subscription={**s,'renew':True}
        else:
            account.subscription={'anchor':now,'cycle':0,'startsAt':now,'endsAt':period_boundary(now,1),
                                  'used':0,'renew':True,'monthlyLimit':plan.monthly_credits,'priceCents':int(plan.price*100)}
        account.save(update_fields=['subscription','updated_at'])
        return Response(account_data(account))


@method_decorator(sensitive_post_parameters('photo'), name='dispatch')
class AIRenders(AIPrivateView):
    @sensitive_variables()
    def post(self, request):
        key=owner(request); serializer=RenderInput(data=request.data);serializer.is_valid(raise_exception=True)
        data=serializer.validated_data;raw,mime=decode_photo(data['photo']);digest=hashlib.sha256(raw).hexdigest()
        expire_stale_jobs()
        with transaction.atomic():
            # Obtain the write lock before reading, also on SQLite where
            # select_for_update itself does not lock a row.
            AIServiceConfig.objects.filter(pk=1).update(revision=F('revision'))
            config=AIServiceConfig.objects.select_for_update().filter(pk=1).first()
            if not config or not config.api_key_ciphertext or not encryption_ready():
                raise GenerationUnavailable('AI generation is not configured. Please contact the store.')
            existing=AIRender.objects.filter(request_key=data['request_key']).defer('input_image','result_image').first()
            if existing:
                if existing.owner_hash!=key or (existing.input_hash,existing.style_code,existing.phone_model)!=(digest,data['style_id'],data['model']):
                    return Response({'detail':'This render request conflicts with an existing request.'},status=409)
                return Response(render_data(existing))
            plan=ai_plan()
            style=AIStyle.objects.filter(code=data['style_id'],active=True).first()
            model=PhoneModel.objects.filter(name=data['model'],active=True,brand__active=True).first()
            template=template_for(data['model'])
            if not style or not style.prompt.strip():
                raise serializers.ValidationError('This AI style is unavailable or has no saved prompt.')
            if not model or not template:
                raise serializers.ValidationError('Choose an available phone model first.')
            if AIRender.objects.filter(owner_hash=key,status__in=['queued','generating']).exists():
                return Response({'detail':'Finish your current render before starting another.'},status=409)
            if AIRender.objects.filter(created_at__gte=timezone.now()-timedelta(days=1)).count()>=settings.AI_DAILY_RENDER_LIMIT:
                return Response({'detail':'The store has reached its daily AI limit. Please try again later.'},status=429)
            if AIRender.objects.filter(status__in=['queued','generating']).count()>=settings.AI_CONCURRENT_RENDER_LIMIT:
                return Response({'detail':'All AI render slots are busy. Please try again shortly.'},status=429)
            account,_=AIAccount.objects.select_for_update().get_or_create(owner_hash=key);refresh_account(account,plan)
            if account.trial_used<plan.trial_credits:
                account.trial_used+=1;allocation={'type':'trial'}
            elif account.subscription and int(timezone.now().timestamp()*1000)<account.subscription['endsAt'] and account.subscription['used']<account.subscription['monthlyLimit']:
                account.subscription={**account.subscription,'used':account.subscription['used']+1}
                allocation={'type':'monthly','period':account.subscription['startsAt']}
            else:
                return Response({'detail':'No AI generations remaining. Subscribe or wait for your next monthly reset.'},status=409)
            account.save(update_fields=['trial_used','subscription','updated_at'])
            job=AIRender.objects.create(request_key=data['request_key'],owner_hash=key,style_code=style.code,
                style_name=style.name,model_name=config.model_name,phone_model=model.name,phone_template_id=template['id'],
                prompt=build_prompt(style,model,template),input_image=raw,input_mime=mime,input_hash=digest,allocation=allocation)
            transaction.on_commit(lambda:dispatch_render(job.id))
        return Response(render_data(job),status=202)


class AIRenderDetail(AIPrivateView):
    def get(self, request, reference):
        key=owner(request);expire_stale_jobs(key)
        return Response(render_data(get_object_or_404(AIRender.objects.defer('input_image','result_image'),pk=reference,owner_hash=key)))

    def post(self, request, reference):
        key=owner(request)
        if request.data!={'action':'cancel'}:
            raise serializers.ValidationError('Unknown render action.')
        with transaction.atomic():
            AIServiceConfig.objects.filter(pk=1).update(revision=F('revision'))
            job=get_object_or_404(AIRender.objects.select_for_update(),pk=reference,owner_hash=key)
            if job.status=='cancelled':return Response(render_data(job))
            if job.status!='queued':return Response({'detail':'Rendering has started. You can leave this page and return when it is ready.'},status=409)
            return Response(render_data(restore_credit(job,'cancelled')))


class AIRenderImage(AIPrivateView):
    def get(self, request, reference):
        job=get_object_or_404(AIRender,pk=reference,owner_hash=owner(request),status='ready')
        response=HttpResponse(bytes(job.result_image),content_type='image/png')
        response['Content-Disposition']=f'inline; filename="ai-{job.id}.png"'
        response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
        return response


@sensitive_variables()
def edit_image(api_key, job):
    boundary='popomo-'+uuid.uuid4().hex
    fields={'model':job.model_name,'prompt':job.prompt,'n':'1','size':'1024x1536',
            'quality':'medium','output_format':'png','background':'opaque','safety_identifier':job.owner_hash}
    body=bytearray()
    for name,value in fields.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[job.input_mime]
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="photo.{ext}"\r\nContent-Type: {job.input_mime}\r\n\r\n'.encode())
    body.extend(bytes(job.input_image));body.extend(f'\r\n--{boundary}--\r\n'.encode())
    request=urllib.request.Request(API_BASE+'/images/edits',data=bytes(body),headers={
        'Authorization':'Bearer '+api_key,'Content-Type':'multipart/form-data; boundary='+boundary,
        'Accept':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=240) as response:
            payload=response.read(32*1024*1024+1);request_id=response.headers.get('x-request-id','')[:150]
        if len(payload)>32*1024*1024:raise ValueError()
        data=json.loads(payload);encoded=data['data'][0]['b64_json'];raw=base64.b64decode(encoded,validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.width*image.height>16_000_000:raise ValueError()
                image.load();output=BytesIO();ImageOps.exif_transpose(image).convert('RGB').save(output,format='PNG')
        return output.getvalue(),request_id
    except urllib.error.HTTPError as error:
        status=error.code
        try:provider_code=json.loads(error.read(16384)).get('error',{}).get('code','')
        except Exception:provider_code=''
        error.close()
        messages={401:('credentials','OpenAI rejected the API key. Please check the saved service configuration.'),
                  403:('permission','OpenAI denied image generation. Check project permissions and model access.'),
                  404:('model','The configured image model is unavailable to this project.'),
                  429:('rate_limit','OpenAI reached a usage or billing limit. Check the API account and try again later.')}
        code,message=messages.get(status,('provider_error','OpenAI could not complete this image. Please retry later.'))
        if provider_code in ('moderation_blocked','content_policy_violation','safety_violations'):
            code,message='content_policy','This image could not be generated under the service content rules. Try a different photo or style.'
        if provider_code in ('insufficient_quota','billing_hard_limit_reached'):
            code,message='quota','The OpenAI API account has insufficient credit or has reached its billing limit.'
        billing_errors={
            'credit_balance_exhausted':'The OpenAI API account has no prepaid credits remaining.',
            'project_spend_limit_exceeded':'This OpenAI API project has reached its spending limit.',
            'organization_spend_limit_exceeded':'The OpenAI API organization has reached its spending limit.',
            'organization_usage_limit_exceeded':'The OpenAI API organization has reached its approved usage limit.',
            'rate_limit_exceeded':'OpenAI has reached the request limit for this model. Please retry later.',
            'slow_down':'OpenAI temporarily limited new requests. Please wait before retrying.',
        }
        if provider_code in billing_errors:
            code,message=provider_code,billing_errors[provider_code]
        raise GenerationError(code,message) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise GenerationError('network','The image service timed out or could not be reached. Please retry later.') from None
    except (ValueError,KeyError,TypeError,IndexError):
        raise GenerationError('invalid_response','The image service returned an unreadable image. Please retry later.') from None


@sensitive_variables()
def run_render(job_id):
    if not AIRender.objects.filter(pk=job_id,status='queued').update(status='generating',started_at=timezone.now()):
        return
    job=AIRender.objects.get(pk=job_id)
    try:
        config=current_config()
        if not config.api_key_ciphertext:
            raise GenerationError('credentials','AI generation is not configured. Please contact the store.')
        result,request_id=edit_image(decrypt_api_key(config),job)
        AIRender.objects.filter(pk=job_id,status='generating').update(status='ready',result_image=result,
            input_image=b'',completed_at=timezone.now(),provider_request_id=request_id)
    except GenerationError as error:
        restore_credit(job,'failed',error.code,error.message)
    except Exception:
        # Never put provider bodies, credentials or uploaded photos into logs/UI.
        restore_credit(job,'failed','internal','The render could not finish. Your generation has been returned. Please retry.')
