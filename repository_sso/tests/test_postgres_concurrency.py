import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from repository_sso.models import SessionBinding
from repository_sso.protocol import refresh_session


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL row locks")
class PostgreSQLRefreshConcurrencyTests(TransactionTestCase):
    def test_simultaneous_refresh_uses_rotating_token_once(self):
        binding = SessionBinding.objects.create(
            session_key="postgres-concurrent-refresh",
            issuer="https://identity.example/realms/repository",
            subject="concurrent-user",
            sid="concurrent-session",
            issued_at=int(time.time()) - 20,
            check_after=0,
            refresh_token="original-refresh",
        )
        workers_ready = threading.Barrier(2)
        calls_lock = threading.Lock()
        refresh_calls = 0

        def token_response(*args, **kwargs):
            nonlocal refresh_calls
            with calls_lock:
                refresh_calls += 1
            # Keep the first transaction open long enough for the second
            # connection to contend for the same select_for_update row lock.
            time.sleep(0.25)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "id_token": "rotated-id-token",
                    "refresh_token": "rotated-refresh",
                },
            )

        def worker():
            close_old_connections()
            try:
                stale = SessionBinding.objects.get(pk=binding.pk)
                workers_ready.wait(timeout=5)
                return refresh_session(None, stale)
            finally:
                connection.close()

        claims = {
            "iss": binding.issuer,
            "aud": "repository",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            "sub": binding.subject,
            "sid": binding.sid,
        }
        with (
            patch("repository_sso.protocol.requests.post", side_effect=token_response),
            patch("repository_sso.protocol.decode_token", return_value=claims),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: worker(), range(2)))

        binding.refresh_from_db()
        self.assertEqual(results, [True, True])
        self.assertEqual(refresh_calls, 1)
        self.assertEqual(binding.refresh_token, "rotated-refresh")
        self.assertGreater(binding.check_after, time.time())
