from django.http import HttpResponse
from django.urls import include, path
from django.contrib.auth.decorators import login_required
from repository_sso import oidc
from repository_sso.models import SessionBinding
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def home(request):
    return HttpResponse(
        "<html><body>"
        + ("Signed in" if request.user.is_authenticated else "Anonymous")
        + '<a href="/account/login/">Login</a><a href="/account/logout/">Logout</a></body></html>'
    )


@login_required(login_url="/account/login/")
def protected(request):
    return HttpResponse("Protected")


admin_patterns = (
    [
        path("", home, name="index"),
        path("login/", home, name="login"),
        path("logout/", home, name="logout"),
    ],
    "admin",
)


urlpatterns = [
    path("", home),
    path("catalogue/", home),
    path("pt/", home),
    path("protected/", protected),
    path("", include("repository_sso.urls")),
    path(
        "account/oidc/<str:provider_id>/login/", oidc.login, name="openid_connect_login"
    ),
    path(
        "account/oidc/<str:provider_id>/login/callback/",
        oidc.callback,
        name="openid_connect_callback",
    ),
    path("admin/", include(admin_patterns, namespace="admin")),
    path("dev-login/", home, name="dev_login"),
    path("account/ajax_login", home, name="account_ajax_login"),
    path("account/", include("allauth.urls")),
]


@csrf_exempt
@require_POST
@login_required(login_url="/account/login/")
def expire_fixture_refresh(request):
    # Synthetic integration fixture only, never included by application URLconf.
    SessionBinding.objects.filter(session_key=request.session.session_key).update(
        check_after=0
    )
    return HttpResponse(status=200)


urlpatterns += [path("fixture/expire-refresh/", expire_fixture_refresh)]
