import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_uppercase_and_underscores(value):
    """
    Validates that the value contains only uppercase letters and underscores.
    """
    if not re.match(r'^[A-Z_]+$', value):
        raise ValidationError(
            _("Must be uppercase letters and underscores only."),
            code='invalid_format'
        )

def validate_uppercase_only(value):
    """
    Validates that the value contains only uppercase letters.
    """
    if not re.match(r'^[A-Z]+$', value):
        raise ValidationError(
            _("Must be uppercase letters only."),
            code='invalid_format'
        )
