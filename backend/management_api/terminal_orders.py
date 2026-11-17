"""Retired terminal-server endpoints. No credentials, claims or state mutation."""
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


@method_decorator(never_cache, name='dispatch')
class RetiredTerminalAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def retired(self, request, **kwargs):
        return Response({'detail': 'Terminal cloud access has been retired. Use the supplier host for display only.'}, status=410)

    get = post = options = retired
