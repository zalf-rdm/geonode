# ruff: noqa: E402
"""Start the isolated Django app used by browser integration tests."""

import os
import sys
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "repository_sso.tests.settings")
import django

django.setup()
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount

call_command("migrate", verbosity=0)
user, _ = get_user_model().objects.get_or_create(
    username="synthetic-user",
    defaults={
        "email": "synthetic@example.test",
        "is_staff": True,
    },
)
SocialAccount.objects.get_or_create(
    user=user, provider="keycloak", uid="synthetic-existing-user"
)


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


make_server(
    "127.0.0.1",
    int(sys.argv[1]),
    get_wsgi_application(),
    server_class=ThreadedServer,
    handler_class=QuietHandler,
).serve_forever()
