from allauth.core.exceptions import ImmediateHttpResponse
from django.http import HttpResponseRedirect


class SilentProbeMixin:
    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        target = request.session.pop("repository_sso_probe", None)
        if target and request.GET.get("error") in (
            "login_required",
            "interaction_required",
            "consent_required",
            "account_selection_required",
        ):
            raise ImmediateHttpResponse(HttpResponseRedirect(target))
        return super().on_authentication_error(
            request,
            provider,
            error=error,
            exception=exception,
            extra_context=extra_context,
        )
