from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import SessionBinding
from .protocol import LOCAL_ADMIN_SESSION, revocations_for


@receiver(user_logged_in, dispatch_uid="repository_sso.bind_session")
def bind_session(sender, request, user, **kwargs):
    if not getattr(settings, "KEYCLOAK_SSO_ENABLED", False):
        return
    pending = getattr(request, "repository_sso_identity", None) or request.session.pop(
        "repository_sso_pending", None
    )
    if not pending:
        # Middleware rejects browser sessions created by other login backends,
        # except the Django admin login of active staff/superusers.
        from .middleware import CentralSSOMiddleware

        if user.is_staff and CentralSSOMiddleware._is_admin_request(request):
            request.session[LOCAL_ADMIN_SESSION] = True
        return
    request.session.pop("repository_sso_pending", None)
    request.session.pop(LOCAL_ADMIN_SESSION, None)
    claims, raw = pending
    if not request.session.session_key:
        request.session.create()
    binding = SessionBinding.objects.update_or_create(
        session_key=request.session.session_key,
        defaults={
            "issuer": claims["iss"],
            "subject": claims["sub"],
            "sid": claims["sid"],
            "issued_at": claims["iat"],
            "revoked": False,
            "id_token": raw,
            "refresh_token": request.session.get("repository_sso_refresh_token", ""),
            "check_after": int(request.session.get("repository_sso_check_after", 0)),
        },
    )[0]
    if revocations_for(binding).exists():
        binding.revoked = True
        binding.save(update_fields=["revoked"])
    request.session.pop("repository_sso_refresh_token", None)
    request.session.pop("repository_sso_check_after", None)
    request.session["repository_sso_id_token"] = raw
    request.session.pop("repository_sso_probe", None)
