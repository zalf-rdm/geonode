#########################################################################
#
# Copyright (C) 2016 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

import taggit

from django import forms
from geonode.base.models import Organization
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.utils.translation import gettext_lazy as _

# Ported in from django-registration
attrs_dict = {"class": "required"}


class ProfileCreationForm(UserCreationForm):
    class Meta:
        model = get_user_model()
        fields = ("username",)


class ProfileChangeForm(UserChangeForm):
    class Meta:
        model = get_user_model()
        fields = "__all__"


class ForgotUsernameForm(forms.Form):
    email = forms.EmailField(widget=forms.TextInput(attrs=dict(attrs_dict, maxlength=75)), label=_("Email Address"))


class ProfileForm(forms.ModelForm):
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.values_list("organization", flat=True),
        required=False,
    )
    keywords = taggit.forms.TagField(
        label=_("Keywords"), required=False, help_text=_("A space or comma-separated list of keywords")
    )

    class Meta:
        model = get_user_model()
        exclude = (
            "user",
            "password",
            "last_login",
            "groups",
            "user_permissions",
            "username",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "language",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization_choices = list(
            Organization.objects.exclude(organization__isnull=True)
            .exclude(organization__exact="")
            .order_by("organization")
            .values_list("organization", flat=True)
        )
        self.fields["organization"].widget.attrs.setdefault("list", "organization-options")
        organization = getattr(self.instance, "organization", None)
        if organization:
            self.fields["organization"].initial = str(organization)

    def clean_organization(self):
        value = self.cleaned_data.get("organization")
        if not value:
            return None
        name = value.strip()
        if not name:
            return None
        organization, _ = Organization.objects.get_or_create(
            organization__iexact=name,
            defaults={"organization": name}
        )
        return organization
