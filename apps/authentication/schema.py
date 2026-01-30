from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.authentication.authentication.SessionJWTAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        # Standard JWT bearer auth for Swagger/Redoc Authorize button
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
