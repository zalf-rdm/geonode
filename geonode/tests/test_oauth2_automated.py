import os
import json
import base64
from django.contrib.auth import get_user_model
from oauth2_provider.models import Application
from django.test import Client, TestCase
from django.urls import reverse

class OAuth2Test(TestCase):
    def setUp(self):
        self.username = "admin"
        self.password = "admin"
        self.user = get_user_model().objects.create_superuser(
            self.username, "admin@example.com", self.password
        )
        self.application = Application.objects.create(
            name="Test App",
            user=self.user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            redirect_uris="http://localhost:8000",
            skip_authorization=True,
        )
        self.client = Client()

    def test_oauth2_token(self):
        # Get Token
        auth = base64.b64encode(f"{self.application.client_id}:{self.application.client_secret}".encode()).decode()
        response = self.client.post(
            reverse("oauth2_provider:token"),
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "scope": "openid",
            },
            HTTP_AUTHORIZATION=f"Basic {auth}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        token = data["access_token"]

        # Use Token
        response = self.client.get(
            reverse("userinfo"),
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        if response.status_code != 200:
            print(f"Response content: {response.content}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preferred_username"], self.username)

        # Test DRF View
        response = self.client.get(
            "/api/v2/users/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        if response.status_code != 200:
            print(f"DRF Response content: {response.content}")
        self.assertEqual(response.status_code, 200)
