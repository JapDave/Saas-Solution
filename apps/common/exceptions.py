from __future__ import annotations
from rest_framework.exceptions import (
    APIException,
    ValidationError,
    PermissionDenied,
    NotFound,
)

from django.utils import timezone
from drf_standardized_errors.formatter import ExceptionFormatter
from drf_standardized_errors.types import ErrorResponse
from rest_framework.exceptions import APIException
from rest_framework.exceptions import ValidationError

# ---- Account codes ----------------------------------------------------------
ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"
INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
ACCOUNT_NAME_EXISTS = "ACCOUNT_NAME_EXISTS"
CONTACT_EMAIL_EXISTS = "CONTACT_EMAIL_EXISTS"
ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS = "ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS"
INVALID_ACCOUNT_DATA = "INVALID_ACCOUNT_DATA"
ACCOUNT_CREATION_FAILED = "ACCOUNT_CREATION_FAILED"
ACCOUNT_UPDATE_FAILED = "ACCOUNT_UPDATE_FAILED"

# ---- Organization codes -----------------------------------------------------
ORGANIZATION_NOT_FOUND = "ORGANIZATION_NOT_FOUND"
ORGANIZATION_NAME_EXISTS = "ORGANIZATION_NAME_EXISTS"
INVALID_ORGANIZATION_DATA = "INVALID_ORGANIZATION_DATA"
ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS = "ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS"
ORGANIZATION_CREATION_FAILED = "ORGANIZATION_CREATION_FAILED"
ORGANIZATION_UPDATE_FAILED = "ORGANIZATION_UPDATE_FAILED"
USER_NOT_ORGANIZATION_MEMBER = "USER_NOT_ORGANIZATION_MEMBER"
ALREADY_ORGANIZATION_OWNER = "ALREADY_ORGANIZATION_OWNER"
INVALID_LOGO_URL = "INVALID_LOGO_URL"


class CodedAPIException(APIException):
    """Base that always returns a dict payload with a 'code'."""

    status_code = 400
    default_code = "ERROR"
    default_detail = "Request failed."

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ):
        if status_code is not None:
            self.status_code = status_code
        payload = {
            "code": code or self.default_code,
            "message": detail or self.default_detail,
        }
        super().__init__(payload)


# ---- Accounts ---------------------------------------------------------------


class InsufficientPermissions(CodedAPIException, PermissionDenied):
    status_code = 403
    default_code = INSUFFICIENT_PERMISSIONS
    default_detail = "User lacks required permissions for operation"


# ---- Organizations ----------------------------------------------------------


# ---- Team codes ----------------------------------------------------------
TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
TEAM_NAME_EXISTS = "TEAM_NAME_EXISTS"
INVALID_TEAM_DATA = "INVALID_TEAM_DATA"
TEAM_SIZE_LIMIT_EXCEEDED = "TEAM_SIZE_LIMIT_EXCEEDED"
SUBSCRIPTION_LIMIT_EXCEEDED = "SUBSCRIPTION_LIMIT_EXCEEDED"
TEAM_CREATION_FAILED = "TEAM_CREATION_FAILED"
TEAM_UPDATE_FAILED = "TEAM_UPDATE_FAILED"

# ---- Role codes -----------------------------------------------------------
ROLE_NOT_FOUND = "ROLE_NOT_FOUND"
ROLE_NAME_CONFLICT = "ROLE_NAME_CONFLICT"
INVALID_ROLE_TYPE = "INVALID_ROLE_TYPE"
INVALID_ROLE_DATA = "INVALID_ROLE_DATA"

# ---- Files codes ----------------------------------------------------------
FILE_NOT_FOUND = "FILE_NOT_FOUND"
INVALID_FILE_DATA = "INVALID_FILE_DATA"
INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
UPLOAD_FAILED = "UPLOAD_FAILED"
VERSION_LIMIT_EXCEEDED = "VERSION_LIMIT_EXCEEDED"

# ---- Subscription codes ---------------------------------------------------
SUBSCRIPTION_NOT_FOUND = "SUBSCRIPTION_NOT_FOUND"
INVALID_SUBSCRIPTION_DATA = "INVALID_SUBSCRIPTION_DATA"

# ---- Agent codes ----------------------------------------------------------
AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
INVALID_AGENT_DATA = "INVALID_AGENT_DATA"
AGENT_VERSION_NOT_FOUND = "AGENT_VERSION_NOT_FOUND"
LLM_NOT_FOUND = "LLM_NOT_FOUND"
LLM_NOT_ENABLED = "LLM_NOT_ENABLED"
TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
TOOL_NOT_ENABLED = "TOOL_NOT_ENABLED"
INVALID_LLM_CONFIGURATION = "INVALID_LLM_CONFIGURATION"
INVALID_TOOL_CONFIGURATION = "INVALID_TOOL_CONFIGURATION"
LLM_REQUIRED = "LLM_REQUIRED"
DUPLICATE_TOOL = "DUPLICATE_TOOL"
INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
LLM_NOT_PERMITTED = "LLM_NOT_PERMITTED"

# ---- Product/Module codes -------------------------------------------------
PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
MODULE_NOT_FOUND = "MODULE_NOT_FOUND"
INVALID_PRODUCT_DATA = "INVALID_PRODUCT_DATA"
INVALID_MODULE_DATA = "INVALID_MODULE_DATA"

# ---- Channel codes --------------------------------------------------------
CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
CHANNEL_NAME_NOT_UNIQUE = "CHANNEL_NAME_NOT_UNIQUE"
CHANNEL_TYPE_NOT_ENABLED = "CHANNEL_TYPE_NOT_ENABLED"
CHANNEL_LIMIT_EXCEEDED = "CHANNEL_LIMIT_EXCEEDED"
CHANNEL_DELETED = "CHANNEL_DELETED"
INVALID_CHANNEL_CONFIGURATION = "INVALID_CHANNEL_CONFIGURATION"
GRANT_NOT_FOUND = "GRANT_NOT_FOUND"
INVALID_GRANT_SUBJECT = "INVALID_GRANT_SUBJECT"
INVALID_CHANNEL_PERMISSION = "INVALID_CHANNEL_PERMISSION"
SYSTEM_MANAGED_FIELD = "SYSTEM_MANAGED_FIELD"
CHANNEL_CONFIGURATION_INCOMPLETE = "CHANNEL_CONFIGURATION_INCOMPLETE"

# ---- Flow codes ------------------------------------------------------------
FLOW_NOT_FOUND = "FLOW_NOT_FOUND"
FLOW_NAME_NOT_UNIQUE = "FLOW_NAME_NOT_UNIQUE"
FLOW_ALREADY_DELETED = "FLOW_ALREADY_DELETED"
FLOW_NOT_DELETED = "FLOW_NOT_DELETED"
FLOW_VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
FLOW_VERSION_CONFLICT = "VERSION_CONFLICT"
PREVIOUS_VERSION_REQUIRED = "PREVIOUS_VERSION_REQUIRED"
INVALID_FLOW_JSON = "INVALID_FLOW_JSON"
NO_ACTIVE_VERSION = "NO_ACTIVE_VERSION"
DRAFT_ALREADY_EXISTS = "DRAFT_ALREADY_EXISTS"
NO_PUBLISHED_VERSION = "NO_PUBLISHED_VERSION"

# ---- Integration codes -----------------------------------------------------
INTEGRATION_NOT_FOUND = "INTEGRATION_NOT_FOUND"
INTEGRATION_NAME_NOT_UNIQUE = "INTEGRATION_NAME_NOT_UNIQUE"
INTEGRATION_TYPE_DISABLED = "INTEGRATION_TYPE_DISABLED"
INTEGRATION_LIMIT_EXCEEDED = "INTEGRATION_LIMIT_EXCEEDED"
INTEGRATION_DELETED = "INTEGRATION_DELETED"
INVALID_INTEGRATION_CONFIGURATION = "INVALID_INTEGRATION_CONFIGURATION"
WEBHOOK_SECRET_ROTATED = "WEBHOOK_SECRET_ROTATED"

# ---- Knowledge Base codes --------------------------------------------------
KB_COLLECTION_NOT_FOUND = "KB_COLLECTION_NOT_FOUND"
KB_RESOURCE_NOT_FOUND = "KB_RESOURCE_NOT_FOUND"
KB_DUPLICATE_RESOURCE = "KB_DUPLICATE_RESOURCE"
KB_LIMIT_EXCEEDED = "KB_LIMIT_EXCEEDED"
KB_INVALID_FILE_TYPE = "KB_INVALID_FILE_TYPE"
KB_FILE_TOO_LARGE = "KB_FILE_TOO_LARGE"
KB_BROKEN_REFERENCE = "KB_BROKEN_REFERENCE"

# ---- Tool codes ------------------------------------------------------------
TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
TOOL_NOT_ENABLED = "TOOL_NOT_ENABLED"
TOOL_ALREADY_ENABLED = "TOOL_ALREADY_ENABLED"
TOOL_ALREADY_DISABLED = "TOOL_ALREADY_DISABLED"
MAX_TOOLS_EXCEEDED = "MAX_TOOLS_EXCEEDED"
TOOL_DUPLICATE = "TOOL_DUPLICATE"
INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
INVALID_UUID_FORMAT = "INVALID_UUID_FORMAT"
INVALID_URL_FORMAT = "INVALID_URL_FORMAT"

# ---- Users --------------------------------------------------------------
USER_NOT_FOUND = "USER_NOT_FOUND"
EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
INVALID_USER_DATA = "INVALID_USER_DATA"
USER_ALREADY_MEMBER = "USER_ALREADY_MEMBER"
USER_NOT_MEMBER = "USER_NOT_MEMBER"
CANNOT_DELETE_OWNER = "CANNOT_DELETE_OWNER"
CANNOT_DEACTIVATE_OWNER = "CANNOT_DEACTIVATE_OWNER"
INVALID_PAGINATION = "INVALID_PAGINATION"
USER_CREATION_FAILED = "USER_CREATION_FAILED"
USER_UPDATE_FAILED = "USER_UPDATE_FAILED"


class CustomValidationError(ValidationError):
    """Common validation error that carries optional extras.

    Note: Our exception_handler maps ValidationError instances to a
    domain-specific INVALID_* code with an "errors" dictionary. This class
    exists to carry optional fields (user_message, developer_message, etc.)
    and to allow setting a non-default status code while remaining a
    ValidationError so the handler logic applies consistently across apps.
    """

    status_code = 400
    default_code = "error"

    def __init__(self, detail=None, code=None, status_code=None, *args, **kwargs):
        # If a code is provided alongside a detail payload (e.g., serializer.errors),
        # wrap it so our exception_handler can pass it through unchanged.
        shaped_detail = detail
        if code is not None and detail is not None:
            # Avoid double-wrapping if detail already contains a code.
            try:
                has_code = isinstance(detail, dict) and "code" in detail
            except Exception:
                has_code = False
            if not has_code:
                shaped_detail = {"code": code, "errors": detail}

        super().__init__(detail=shaped_detail, code=code)

        if status_code is not None:
            self.status_code = status_code

        if kwargs.get("message"):
            # Allow callers to attach a friendly message; handler may choose it.
            self.message = kwargs.get("message")

        if kwargs.get("user_message"):
            self.user_message = kwargs.get("user_message")

        if kwargs.get("developer_message"):
            self.developer_message = kwargs.get("developer_message")

        if kwargs.get("internal_error_code"):
            self.internal_error_code = kwargs.get("internal_error_code")


class CustomError(CodedAPIException):
    """Common coded error used across apps.

    This wraps DRF APIException with a consistent payload shape that our
    exception_handler recognizes and passes through: {"code", "message"}.
    It also supports optional user/developer messages for telemetry/UX.
    """

    status_code = 400
    default_code = "error"
    default_detail = "Request failed."

    def __init__(self, detail=None, code=None, status_code=None, *args, **kwargs):
        # Prefer an explicit "message" kwarg over positional detail if given.
        message = kwargs.get("message", detail)
        super().__init__(detail=message, code=code, status_code=status_code)

        # Attach optional metadata for formatters/consumers.
        if kwargs.get("user_message"):
            self.user_message = kwargs.get("user_message")

        if kwargs.get("developer_message"):
            self.developer_message = kwargs.get("developer_message")

        if kwargs.get("internal_error_code"):
            self.internal_error_code = kwargs.get("internal_error_code")


class CustomExceptionFormatter(ExceptionFormatter):
    def format_error_response(self, error_response: ErrorResponse):
        """
        Format response
        """
        exc = self.exc
        more_info = None
        user_message = None
        developer_message = None
        status_code = None

        if hasattr(self.original_exc, "status_code"):
            status_code = self.original_exc.status_code

        if hasattr(exc, "user_message"):
            user_message = exc.user_message

        if hasattr(exc, "developer_message"):
            developer_message = exc.developer_message

        if hasattr(exc, "internal_error_code"):
            status_code = exc.internal_error_code

        error = error_response.errors[0]

        if hasattr(exc, "message"):
            message = exc.message
        else:
            message = error.detail
            user_message = message

        if error_response.type == "validation_error":
            # for validation error add error to more_info
            more_info = [
                {
                    "code": err.code,
                    "field": err.attr,
                    "issue": err.detail,
                }
                for err in error_response.errors
            ]

        return {
            "status": "Error",
            "status_code": status_code,
            "message": message,
            "details": {
                "user_message": user_message,
                "developer_message": developer_message,
                "more_info": more_info,
            },
            "timestamp": timezone.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }


def get_single_error(data: dict):
    """
    return first single message of rest_framework serializer.errors.
    """
    for value in data.values():
        return value[0]
    return ""
