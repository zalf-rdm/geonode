"""Display-name and ORCID fields on the user API (#702).

A landing page showed the bare ORCID iD where a person's name belongs. The client's
display chain is ``full_name || first_name + last_name || username``, and for an ORCID
login the username *is* the iD -- so with ``full_name`` missing from the payload and no
first/last name on the profile, the iD was what got rendered.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from django.test.client import RequestFactory

from geonode.people.api.serializers import UserSerializer

User = get_user_model()

ORCID_ID = "0000-0002-1825-0097"


# Pinned rather than inherited: deployments point this at sandbox.orcid.org, and a test
# asserting the ambient value passes or fails depending on the environment.
@override_settings(SOCIALACCOUNT_ORCID_BASE_URL="https://orcid.org")
class UserSerializerDisplayFieldsTest(TestCase):
    def setUp(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.context = {"request": request}

    def serialize(self, user):
        return UserSerializer(context=self.context).to_representation(user)

    def make_user(self, username, **kwargs):
        return User.objects.create(username=username, **kwargs)

    def test_full_name_is_served(self):
        """The client's first branch; it was absent from the payload entirely."""
        user = self.make_user(ORCID_ID, first_name="Josiah", last_name="Carberry")
        self.assertEqual("Josiah Carberry", self.serialize(user)["full_name"])

    def test_full_name_is_empty_rather_than_the_username(self):
        """Falling back to the username here would render an ORCID iD as if it were a name."""
        user = self.make_user(ORCID_ID, orcid_identifier=ORCID_ID)
        self.assertEqual("", self.serialize(user)["full_name"])

    def test_full_name_with_only_one_of_the_two_names(self):
        user = self.make_user("only-last", last_name="Carberry")
        self.assertEqual("Carberry", self.serialize(user)["full_name"])

    def test_orcid_url_is_served(self):
        user = self.make_user(ORCID_ID, orcid_identifier=ORCID_ID)
        self.assertEqual(f"https://orcid.org/{ORCID_ID}", self.serialize(user)["orcid_url"])

    def test_orcid_url_is_empty_without_an_identifier(self):
        self.assertEqual("", self.serialize(self.make_user("no-orcid"))["orcid_url"])

    @override_settings(SOCIALACCOUNT_ORCID_BASE_URL="https://sandbox.orcid.org")
    def test_orcid_url_follows_the_configured_base_url(self):
        """Built server-side so sandbox deployments do not link to production orcid.org."""
        user = self.make_user(ORCID_ID, orcid_identifier=ORCID_ID)
        self.assertEqual(f"https://sandbox.orcid.org/{ORCID_ID}", self.serialize(user)["orcid_url"])

    def test_anonymous_viewers_receive_the_display_fields(self):
        """Landing pages are public, so the fix has to survive the unauthenticated path."""
        user = self.make_user(ORCID_ID, first_name="Josiah", last_name="Carberry", orcid_identifier=ORCID_ID)
        data = self.serialize(user)
        self.assertEqual("Josiah Carberry", data["full_name"])
        self.assertEqual(f"https://orcid.org/{ORCID_ID}", data["orcid_url"])

    def test_client_display_chain_no_longer_yields_the_orcid_id(self):
        """Replicates the client's chain to pin the actual regression."""
        user = self.make_user(ORCID_ID, first_name="Josiah", last_name="Carberry", orcid_identifier=ORCID_ID)
        data = self.serialize(user)

        shown = (
            data.get("full_name")
            or " ".join(x for x in (data.get("first_name"), data.get("last_name")) if x)
            or data.get("username")
        )
        self.assertEqual("Josiah Carberry", shown)
        self.assertNotEqual(ORCID_ID, shown)
