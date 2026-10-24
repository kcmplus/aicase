from rest_framework.permissions import DjangoModelPermissions, BasePermission

class ModelPermissions(DjangoModelPermissions):
    perms_map = {**DjangoModelPermissions.perms_map,
                 "GET": ["%(app_label)s.view_%(model_name)s"],
                 "HEAD": ["%(app_label)s.view_%(model_name)s"],
                 "OPTIONS": ["%(app_label)s.view_%(model_name)s"]}

class AccessAdministration(BasePermission):
    """Only superusers can change accounts or grants; roles cannot grant themselves power."""
    def has_permission(self, request, view):
        return request.method in ("GET", "HEAD", "OPTIONS") or request.user.is_superuser
