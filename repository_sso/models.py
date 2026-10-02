from django.db import models


class SessionBinding(models.Model):
    """Link an application session to the authenticated Keycloak session."""

    session_key = models.CharField(max_length=64, primary_key=True)
    issuer = models.CharField(max_length=512)
    subject = models.CharField(max_length=255, db_index=True)
    sid = models.CharField(max_length=255, db_index=True)
    issued_at = models.BigIntegerField()
    revoked = models.BooleanField(default=False)
    id_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    check_after = models.BigIntegerField(default=0)


class LogoutEvent(models.Model):
    """Durable replay protection and revocations, including callbacks in flight."""

    digest = models.CharField(max_length=64, primary_key=True)
    issuer = models.CharField(max_length=512)
    subject = models.CharField(max_length=255, blank=True, db_index=True)
    sid = models.CharField(max_length=255, blank=True, db_index=True)
    issued_at = models.BigIntegerField()
    received_at = models.DateTimeField(auto_now_add=True)
