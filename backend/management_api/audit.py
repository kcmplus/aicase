from .models import AuditLog

def audit(request, action, resource, obj=None, summary=""):
    AuditLog.objects.create(actor=request.user if request.user.is_authenticated else None,
        actor_name=request.user.username if request.user.is_authenticated else "anonymous",
        action=action, resource=resource, object_id=str(obj.pk) if obj else "", summary=summary[:300])
