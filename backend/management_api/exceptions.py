from django.db.models.deletion import ProtectedError
from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

def exception_handler(exc, context):
    if isinstance(exc, IntegrityError) and any(name in str(exc) for name in ("one_active_plan_per_kind", "management_api_pricingplan.kind")):
        return Response({"detail": "此类型已有启用套餐，请刷新后重试。"}, status=409)
    if isinstance(exc, ProtectedError):
        return Response({"detail": "该记录仍被其他数据引用，请先调整关联，或改为停用。"}, status=409)
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and hasattr(exc, "get_codes"):
        code = exc.get_codes()
        if isinstance(code, str):
            response.data["code"] = code
    return response
