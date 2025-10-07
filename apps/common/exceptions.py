from __future__ import annotations
from rest_framework.exceptions import APIException, ValidationError, PermissionDenied, NotFound

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

    def __init__(self, detail: str | None = None, *, code: str | None = None, status_code: int | None = None):
        if status_code is not None:
            self.status_code = status_code
        payload = {"code": code or self.default_code, "message": detail or self.default_detail}
        super().__init__(payload)


# ---- Accounts ---------------------------------------------------------------

class AccountNotFound(CodedAPIException, NotFound):
    status_code = 404
    default_code = ACCOUNT_NOT_FOUND
    default_detail = "Account does not exist or has been deleted"


class InsufficientPermissions(CodedAPIException, PermissionDenied):
    status_code = 403
    default_code = INSUFFICIENT_PERMISSIONS
    default_detail = "User lacks required permissions for operation"


class InvalidAccountData(CodedAPIException, ValidationError):
    status_code = 400
    default_code = INVALID_ACCOUNT_DATA
    default_detail = "Account data validation failed"


class AccountNameExists(CodedAPIException):
    status_code = 400
    default_code = ACCOUNT_NAME_EXISTS
    default_detail = "Account name already exists in the platform"


class ContactEmailExists(CodedAPIException):
    status_code = 400
    default_code = CONTACT_EMAIL_EXISTS
    default_detail = "Contact email already exists in the platform"


class AccountHasActiveSubscriptions(CodedAPIException):
    status_code = 409
    default_code = ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS
    default_detail = "Cannot deactivate/delete account with active subscriptions"


class AccountCreationFailed(CodedAPIException):
    status_code = 400
    default_code = ACCOUNT_CREATION_FAILED
    default_detail = "Account creation process failed"


class AccountUpdateFailed(CodedAPIException):
    status_code = 400
    default_code = ACCOUNT_UPDATE_FAILED
    default_detail = "Account update process failed"


# ---- Organizations ----------------------------------------------------------

class OrganizationNotFound(CodedAPIException, NotFound):
    status_code = 404
    default_code = ORGANIZATION_NOT_FOUND
    default_detail = "Organization does not exist or has been deleted"


class InvalidOrganizationData(CodedAPIException, ValidationError):
    status_code = 400
    default_code = INVALID_ORGANIZATION_DATA
    default_detail = "Organization data validation failed"


class OrganizationNameExists(CodedAPIException):
    status_code = 409
    default_code = ORGANIZATION_NAME_EXISTS
    default_detail = "Organization name already exists in the account"


class OrganizationHasActiveSubscriptions(CodedAPIException):
    status_code = 409
    default_code = ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS
    default_detail = "Cannot deactivate/delete organization with active subscriptions"


class OrganizationCreationFailed(CodedAPIException):
    status_code = 400
    default_code = ORGANIZATION_CREATION_FAILED
    default_detail = "Organization creation process failed"


class OrganizationUpdateFailed(CodedAPIException):
    status_code = 400
    default_code = ORGANIZATION_UPDATE_FAILED
    default_detail = "Organization update process failed"


class UserNotOrganizationMember(CodedAPIException):
    status_code = 400
    default_code = USER_NOT_ORGANIZATION_MEMBER
    default_detail = "Target user is not a member of the organization"


class AlreadyOrganizationOwner(CodedAPIException):
    status_code = 400
    default_code = ALREADY_ORGANIZATION_OWNER
    default_detail = "User is already the organization owner"


class InvalidLogoUrl(CodedAPIException):
    status_code = 400
    default_code = INVALID_LOGO_URL
    default_detail = "Logo URL is invalid or inaccessible"
# ---- Team codes ----------------------------------------------------------
TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
TEAM_NAME_EXISTS = "TEAM_NAME_EXISTS"
INVALID_TEAM_DATA = "INVALID_TEAM_DATA"
TEAM_SIZE_LIMIT_EXCEEDED = "TEAM_SIZE_LIMIT_EXCEEDED"
SUBSCRIPTION_LIMIT_EXCEEDED = "SUBSCRIPTION_LIMIT_EXCEEDED"


class TeamNotFound(CodedAPIException, NotFound):
    status_code = 404
    default_code = TEAM_NOT_FOUND
    default_detail = "Team does not exist or has been deleted"


class InvalidTeamData(CodedAPIException, ValidationError):
    status_code = 400
    default_code = INVALID_TEAM_DATA
    default_detail = "Team data validation failed"


class TeamNameExists(CodedAPIException):
    status_code = 409
    default_code = TEAM_NAME_EXISTS
    default_detail = "Team name already exists within the organization"


class TeamSizeLimitExceeded(CodedAPIException):
    status_code = 400
    default_code = TEAM_SIZE_LIMIT_EXCEEDED
    default_detail = "Team size exceeds subscription limits"


class SubscriptionLimitExceeded(CodedAPIException):
    status_code = 409
    default_code = SUBSCRIPTION_LIMIT_EXCEEDED
    default_detail = "Organization subscription limits prevent this operation"


# ---- Users --------------------------------------------------------------
USER_NOT_FOUND = "USER_NOT_FOUND"
EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
INVALID_USER_DATA = "INVALID_USER_DATA"
USER_ALREADY_MEMBER = "USER_ALREADY_MEMBER"
USER_NOT_MEMBER = "USER_NOT_MEMBER"
CANNOT_DELETE_OWNER = "CANNOT_DELETE_OWNER"
CANNOT_DEACTIVATE_OWNER = "CANNOT_DEACTIVATE_OWNER"
INVALID_PAGINATION = "INVALID_PAGINATION"


class UserNotFound(CodedAPIException, NotFound):
    status_code = 404
    default_code = USER_NOT_FOUND
    default_detail = "User does not exist or has been deleted"


class InvalidUserData(CodedAPIException, ValidationError):
    status_code = 400
    default_code = INVALID_USER_DATA
    default_detail = "User data validation failed"


class EmailAlreadyExists(CodedAPIException):
    status_code = 409
    default_code = EMAIL_ALREADY_EXISTS
    default_detail = "Email address is already in use"


class UserAlreadyMember(CodedAPIException):
    status_code = 409
    default_code = USER_ALREADY_MEMBER
    default_detail = "User is already a member of the organization"


class UserNotMember(CodedAPIException):
    status_code = 400
    default_code = USER_NOT_MEMBER
    default_detail = "User is not a member of the organization"


class CannotDeleteOwner(CodedAPIException):
    status_code = 400
    default_code = CANNOT_DELETE_OWNER
    default_detail = "Cannot delete account or organization owner"


class CannotDeactivateOwner(CodedAPIException):
    status_code = 400
    default_code = CANNOT_DEACTIVATE_OWNER
    default_detail = "Cannot deactivate account or organization owner"


class InvalidPagination(CodedAPIException, ValidationError):
    status_code = 400
    default_code = INVALID_PAGINATION
    default_detail = "Invalid pagination parameters provided"
