from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Link a vetted Keycloak subject to an existing local account; dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", required=True)
        parser.add_argument("--subject", required=True)
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        subject = options["subject"].strip()
        if not subject or len(subject) > 255:
            raise CommandError(
                "Provide a valid Keycloak subject from a vetted realm export."
            )
        try:
            user = (
                get_user_model().objects.select_for_update().get(pk=options["user_id"])
            )
        except (get_user_model().DoesNotExist, ValueError) as exc:
            raise CommandError("The local user does not exist.") from exc
        provider = settings.KEYCLOAK_SSO_PROVIDER_ID
        existing = SocialAccount.objects.filter(provider=provider, uid=subject).first()
        if existing:
            if existing.user_id != user.pk:
                raise CommandError(
                    "This Keycloak subject is already linked to another local user."
                )
            self.stdout.write("Identity already linked; no change.")
            return
        if SocialAccount.objects.filter(provider=provider, user=user).exists():
            raise CommandError(
                "This local user already has a different identity for this provider."
            )
        if options["apply"]:
            SocialAccount.objects.create(provider=provider, uid=subject, user=user)
            self.stdout.write("Identity linked. User data and permissions preserved.")
        else:
            self.stdout.write(
                "Dry run passed. Use --apply after verifying the user/subject pairing."
            )
