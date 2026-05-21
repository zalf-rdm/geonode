#         Copyright (C) 2026 52°North Spatial Information Research GmbH
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     If the program is linked with libraries which are licensed under one
#     of the following licenses, the combination of the program with the
#     linked library is not considered a "derivative work" of the program:
#
#         - Apache License, version 2.0
#         - Apache Software License, version 1.0
#         - GNU Lesser General Public License, version 3
#         - Mozilla Public License, versions 1.0, 1.1 and 2.0
#         - Common Development and Distribution License (CDDL), version 1.0
#
#     Therefore the distribution of the program linked with libraries licensed
#     under the aforementioned licenses, is permitted by the copyright holders
#     if the distribution is compliant with both the GNU General Public License
#     version 2 and the aforementioned licenses.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program. If not, see <https://www.gnu.org/licenses/>.

from urllib.parse import urlparse

from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class KeycloakSilentSSOMiddleware:
    """
    Maintains a hint cookie, that indicates that SSO is possible

    Add zalf.middleware.KeycloakSilentSSOMiddleware to MIDDLEWARE
    before allauth.account.middleware.AccountMiddleware
    """

    def _sso_cookie_domain(self):
        """
        django.conf.settings.SITE_URL and .SITEURL are not standardized, hence both are possible:

        https://docs.djangoproject.com/en/4.2/ref/settings/

        Extracts the SSO cookie domain from the site's URL, defaulting to localhost
        """

        site_url = (
            settings.SITE_URL
            if getattr(settings, "SITE_URL", False)
            else getattr(settings, "SITEURL", "localhost")
        )
        sso_cookie_domain = f".{'.'.join(urlparse(site_url).netloc.split(':')[0].split('.')[1:])}"
        logger.debug(f"Domain for cookie: '{sso_cookie_domain}'")
        return sso_cookie_domain

    def __init__(self, get_response):
        self.get_response = get_response
        self.sso_cookie_domain = self._get_sso_cookie_domain()

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.method == "POST"
            and "/account/logout/" in request.path
            and request.COOKIES.get("sso_hint") == "true"
        ):
            logger.debug("deleting cookie")
            response.delete_cookie("sso_hint", domain=self.sso_cookie_domain, path="/")

        elif (
            request.user.is_authenticated
            and "text/html" in request.META.get("HTTP_ACCEPT", "")
        ):
            logger.debug("refreshing sso_hint cookie")
            sso_cookie_max_age = getattr(settings, "SESSION_COOKIE_AGE", 3600)
            response.set_cookie(
                "sso_hint",
                "true",
                domain=self.sso_cookie_domain,
                max_age=sso_cookie_max_age,
                samesite="Lax",
                path="/",
                secure=request.is_secure(),
                httponly=False,
            )

        return response
