# from geonode.base.api.serializers import BaseDynamicModelSerializer
# import geonode.base.api.serializers as base_serializers
import logging
from django.contrib.auth.password_validation import validate_password
from django.forms import ValidationError as ValidationErrorForm
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.conf import settings
import geonode.base.api.serializers as base_serializers
from dynamic_rest.fields.fields import DynamicRelationField
from geonode.base.models import Organization

logger = logging.getLogger(__name__)


class OrganizationRelationField(DynamicRelationField):
    """Allow linking organizations by ROR identifier when creating users."""

    def to_internal_value_single(self, data, serializer):
        lookup = {}
        if isinstance(data, dict):
            ror = data.get("ror")
            name = data.get("organization") or data.get("name")
            if ror:
                lookup["ror"] = ror
            elif name:
                lookup["organization__iexact"] = name
            else:
                raise serializers.ValidationError("organization payload requires 'ror' or 'organization'/'name' keys")
        elif isinstance(data, str):
            if data.isdigit():
                return super().to_internal_value_single(data, serializer)
            lookup["organization__iexact"] = data

        if lookup:
            try:
                organization = Organization.objects.get(**lookup)
            except Organization.DoesNotExist as exc:
                raise serializers.ValidationError("organization not found for provided identifier") from exc
            except Organization.MultipleObjectsReturned as exc:
                raise serializers.ValidationError(
                    "multiple organizations match provided identifier; please use a unique ror"
                ) from exc
            data = organization.pk
        return super().to_internal_value_single(data, serializer)


class UserSerializer(base_serializers.DynamicModelSerializer):
    link = base_serializers.AutoLinkField(read_only=True)

    class Meta:
        ref_name = "UserProfile"
        model = get_user_model()
        name = "user"
        view_name = "users-list"
        fields = (
            "pk",
            "username",
            "first_name",
            "last_name",
            "department",
            "avatar",
            "organization",
            "perms",
            "is_superuser",
            "is_staff",
            "email",
            "link",
        )
        extra_kwargs = {
            "username": {"validators": []},
            "email": {"validators": []},
        }

    @staticmethod
    def password_validation(password_payload):
        try:
            validate_password(password_payload)
        except ValidationErrorForm as err:
            raise serializers.ValidationError(detail=",".join(err.messages))
        return make_password(password_payload)

    def validate(self, data):
        request = self.context["request"]
        user = request.user
        user_model = get_user_model()
        instance = getattr(self, "instance", None)
        # only admins/staff can edit these permissions
        if not (user.is_superuser or user.is_staff):
            data.pop("is_superuser", None)
            data.pop("is_staff", None)
        # username cant be changed
        if request.method in ("PUT", "PATCH") and data.get("username"):
            raise serializers.ValidationError(detail="username cannot be updated")
        email = data.get("email")
        # Email is required on post
        if request.method in ("POST") and settings.ACCOUNT_EMAIL_REQUIRED and not email:
            raise serializers.ValidationError(detail="email missing from payload")
        # enforce username uniqueness on create
        if request.method == "POST":
            username = data.get("username")
            if username and user_model.objects.filter(username__iexact=username).exists():
                raise serializers.ValidationError(
                    {
                        "detail": f"A user with username '{username}' already exists.",
                        "username": ["A user is already registered with that username."],
                    }
                )

        # email should be unique
        if email:
            email_conflict = user_model.objects.filter(email__iexact=email)
            if instance:
                email_conflict = email_conflict.exclude(pk=instance.pk)
            if email_conflict.exists():
                raise serializers.ValidationError(
                    {
                        "detail": f"A user with email '{email}' already exists.",
                        "email": ["A user is already registered with that email."],
                    }
                )
        # password validation
        password = request.data.get("password")
        if password:
            data["password"] = self.password_validation(password)
        return data

    @classmethod
    def setup_eager_loading(cls, queryset):
        """Perform necessary eager loading of data."""
        queryset = queryset.prefetch_related()
        return queryset

    def to_representation(self, instance):
        # Dehydrate users private fields
        request = self.context.get("request")
        data = super().to_representation(instance)
        if not request or not request.user or not request.user.is_authenticated:
            if "perms" in data:
                del data["perms"]
        elif not request.user.is_superuser and not request.user.is_staff:
            if data["username"] != request.user.username:
                if "perms" in data:
                    del data["perms"]
        return data

    avatar = base_serializers.AvatarUrlField(240, read_only=True)
    organization = OrganizationRelationField(base_serializers.OrganizationSerializer, embed=True, many=False)
