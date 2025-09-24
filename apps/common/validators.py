from django.conf import settings

def email_has_allowed_system_domain(email: str) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.split("@", 1)[1].lower()
    return domain in getattr(settings, "SYSTEM_EMAIL_DOMAINS", set())
