from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DataError, IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .media_hardening import AssetValidationError


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, AssetValidationError):
        return Response({"detail": str(exc)}, status=400)
    if isinstance(exc, DjangoValidationError):
        detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None)
        return Response({"detail": detail or "提交的数据未通过校验。"}, status=400)
    if isinstance(exc, DataError):
        return Response({"detail": "提交的数据超出数据库字段范围。"}, status=400)
    if isinstance(exc, IntegrityError):
        return Response({"detail": "该操作与现有数据约束冲突。"}, status=409)
    return None
