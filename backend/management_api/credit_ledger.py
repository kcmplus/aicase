"""Append-only credit events, written in the same transaction as quota changes.

Callers hold the AIAccount row lock. Admin-only reasons are never returned to
customers. Each balance is for one credit pool, not a mixed monetary balance.
"""
from django.utils import timezone
from rest_framework import serializers
from .models import CreditEntry


def balance(account, pool):
    if pool == 'gift':
        return max(0, account.trial_granted + account.bonus_granted - account.trial_used)
    s = account.subscription
    return max(0, s['monthlyLimit'] - s['used']) if s and not s.get('ledger_expired') else 0


def record(account, key, kind, pool, before, after, **extra):
    return CreditEntry.objects.create(account=account, event_key=key, kind=kind, pool=pool,
                                     amount=after-before, balance_before=before, balance_after=after, **extra)


def ensure_opening(account, pool):
    if not account.credit_entries.filter(pool=pool).exists():
        record(account, 'opening:'+pool, 'opening', pool, 0, balance(account, pool),
               period=account.subscription.get('startsAt') if pool == 'monthly' and account.subscription else None)


def expire_monthly(account, now=None):
    s = account.subscription
    now = now if now is not None else int(timezone.now().timestamp()*1000)
    if s and now >= s['endsAt'] and not s.get('ledger_expired'):
        ensure_opening(account, 'monthly')
        before = balance(account, 'monthly')
        account.subscription = {**s, 'ledger_expired': True}
        account.save(update_fields=['subscription', 'updated_at'])
        record(account, f"expire:{s['startsAt']}", 'expiry', 'monthly', before, 0, period=s['startsAt'])


def entries_page(account, request, *, admin=False):
    qs = account.credit_entries.all() if account else CreditEntry.objects.none()
    cursor = request.query_params.get('before')
    if cursor is not None:
        cursor = serializers.IntegerField(min_value=1, max_value=9223372036854775807).run_validation(cursor)
        qs = qs.filter(pk__lt=cursor)
    rows = list(qs[:21])
    result = []
    for row in rows[:20]:
        item = {'id': row.pk, 'kind': row.kind, 'pool': row.pool, 'amount': row.amount,
                'balanceBefore': row.balance_before, 'balanceAfter': row.balance_after,
                'period': row.period, 'renderId': str(row.render_id) if row.render_id else None,
                'createdAt': row.created_at.isoformat()}
        if admin:
            item.update(reason=row.reason, actorName=row.actor_name)
        result.append(item)
    return {'results': result, 'nextCursor': rows[19].pk if len(rows)>20 else None}
