"""Staff customer directory. Customer accounts never grant staff access."""
import hashlib
from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAdminUser
from rest_framework.response import Response
from .models import Customer, AIAccount, AIRender, AuditLog
from .audit import audit
from .credit_ledger import balance, ensure_opening, record, entries_page


class CustomerPermissions(BasePermission):
    def has_permission(self, request, view):
        if view.action == 'grant':
            return request.user.is_superuser
        perm = 'view' if request.method in ('GET', 'HEAD', 'OPTIONS') else 'change'
        return request.user.has_perm(f'management_api.{perm}_customer')


def credit_summary(customer):
    account = getattr(customer, 'aiaccount', None)
    return {'welcome_granted': account.trial_granted if account else 0,
            'bonus_granted': account.bonus_granted if account else 0,
            'used': account.trial_used if account else 0,
            'remaining': max(0, account.trial_granted + account.bonus_granted - account.trial_used) if account else 0}


class CustomerSerializer(serializers.ModelSerializer):
    credits = serializers.SerializerMethodField()
    def get_credits(self, customer):
        return credit_summary(customer)
    class Meta:
        model = Customer
        fields = ['id', 'email', 'display_name', 'active', 'notes', 'created_at', 'verified_at', 'last_login_at', 'revision', 'credits']
        read_only_fields = fields


class CustomerUpdate(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    active = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=1000, allow_blank=True, required=False)


class CreditGrant(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    amount = serializers.IntegerField(min_value=1, max_value=1000)
    reason = serializers.CharField(max_length=200)


class CustomerViewSet(viewsets.GenericViewSet):
    queryset = Customer.objects.select_related('aiaccount').order_by('-created_at', '-id')
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser, CustomerPermissions]
    search_fields = ['email', 'display_name']
    ordering_fields = ['created_at', 'last_login_at', 'email']
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        active = self.request.query_params.get('active')
        return qs.filter(active=active == 'true') if active in ('true', 'false') else qs

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def retrieve(self, request, pk=None):
        customer = self.get_object()
        result = dict(self.get_serializer(customer).data)
        account = getattr(customer, 'aiaccount', None)
        # Explicit metadata fields only: never expose uploaded photos, prompts or keys.
        result['recent_renders'] = list(AIRender.objects.filter(owner_hash=account.pk).order_by('-created_at').values(
            'id', 'style_name', 'phone_model', 'status', 'created_at', 'credit_restored')[:20]) if account else []
        result['history'] = list(AuditLog.objects.filter(resource='management_api.customer', object_id=str(customer.pk)).values(
            'id', 'actor_name', 'summary', 'created_at')[:20])
        result['subscription'] = ({k: account.subscription.get(k) for k in ['monthlyLimit', 'used', 'endsAt', 'renew']}
                                  if account and account.subscription else None)
        return Response(result)

    @action(detail=True, methods=['get'])
    def credits(self, request, pk=None):
        customer = self.get_object()
        from .models import PricingPlan
        from .ai_generation import refresh_account, expire_stale_jobs
        account = getattr(customer, 'aiaccount', None)
        if account:
            expire_stale_jobs(account.pk)
            refresh_account(account, PricingPlan.objects.filter(kind='ai_monthly', active=True).first())
        return Response(entries_page(account, request, admin=True))

    @transaction.atomic
    def partial_update(self, request, pk=None):
        if set(request.data) - set(CustomerUpdate().fields):
            raise serializers.ValidationError('只能修改账号状态和客服备注。')
        data = CustomerUpdate(data=request.data)
        data.is_valid(raise_exception=True)
        original = self.get_object()
        customer = Customer.objects.select_for_update().get(pk=original.pk)
        if customer.revision != data.validated_data['revision']:
            return Response({'detail': '用户信息已更新，请重新打开详情。'}, status=409)
        for key in ('active', 'notes'):
            if key in data.validated_data:
                setattr(customer, key, data.validated_data[key])
        if original.active and not customer.active:
            customer.session_version += 1
        customer.revision += 1
        customer.save(update_fields=['active', 'notes', 'session_version', 'revision', 'updated_at'])
        audit(request, 'update', 'management_api.customer', customer,
              ('启用顾客账号' if customer.active else '停用顾客账号') + '；更新客服设置')
        return Response(self.get_serializer(Customer.objects.select_related('aiaccount').get(pk=customer.pk)).data)

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def grant(self, request, pk=None):
        data = CreditGrant(data=request.data)
        data.is_valid(raise_exception=True)
        original = self.get_object()
        customer = Customer.objects.select_for_update().get(pk=original.pk)
        if customer.revision != data.validated_data['revision']:
            return Response({'detail': '用户信息已更新，请重新打开详情；请勿重复补发。'}, status=409)
        if not customer.active:
            raise serializers.ValidationError('请先启用账号，再补发次数。')
        account, _ = AIAccount.objects.get_or_create(customer=customer, defaults={
            'owner_hash': hashlib.sha256(('customer:' + str(customer.pk)).encode()).hexdigest()})
        account = AIAccount.objects.select_for_update().get(pk=account.pk)
        ensure_opening(account, 'gift')
        before = balance(account, 'gift')
        account.bonus_granted += data.validated_data['amount']
        account.save(update_fields=['bonus_granted', 'updated_at'])
        record(account, f'grant:{customer.revision}', 'grant', 'gift', before, balance(account, 'gift'),
               actor_name=request.user.username, reason=data.validated_data['reason'])
        customer.revision += 1
        customer.save(update_fields=['revision', 'updated_at'])
        audit(request, 'update', 'management_api.customer', customer,
              f"补发 {data.validated_data['amount']} 次 AI 额度：{data.validated_data['reason']}")
        return Response(self.get_serializer(Customer.objects.select_related('aiaccount').get(pk=customer.pk)).data)
