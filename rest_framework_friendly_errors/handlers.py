from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException

from rest_framework_friendly_errors import settings
from rest_framework_friendly_errors.utils import is_pretty


def drf_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if not response and settings.CATCH_ALL_EXCEPTIONS:
        exc = APIException(exc)
        response = exception_handler(exc, context)

    if response is not None:
        if is_pretty(response):
            return response
        error_message = response.data.get('detail', 'errors')
        error_code = settings.FRIENDLY_EXCEPTION_DICT.get(
            exc.__class__.__name__)
        response.data.pop('detail', {})
        if not response.data:
            response.data['code'] = error_code
            response.data['detail'] = error_message
            # response.data['status_code'] = response.status_code
        elif 'code' in response.data:
            response.data = {
                'code': error_code,
                'detail': error_message
            }
    return response
