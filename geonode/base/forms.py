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
import logging

from dal import autocomplete
from django import forms
from django.forms.fields import MultipleChoiceField
from django.utils.translation import gettext_lazy as _

from geonode.base.models import (
    ResourceBase,
)
from geonode.layers.models import Dataset

logger = logging.getLogger(__name__)


def get_user_choices():
    try:
        return [(x.pk, x.title) for x in Dataset.objects.all().order_by("id")]
    except Exception:
        return []


class UserAndGroupPermissionsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["layers"].label_from_instance = self.label_from_instance

    layers = MultipleChoiceField(
        choices=get_user_choices,
        widget=autocomplete.Select2Multiple(url="datasets_autocomplete"),
        label="Datasets",
        required=False,
    )

    permission_type = forms.ChoiceField(
        required=True,
        widget=forms.RadioSelect,
        choices=(
            ("view", "View"),
            ("download", "Download"),
            ("edit", "Edit"),
        ),
    )
    mode = forms.ChoiceField(
        required=True,
        widget=forms.RadioSelect,
        choices=(
            ("set", "Set"),
            ("unset", "Unset"),
        ),
    )
    ids = forms.CharField(required=False, widget=forms.HiddenInput())

    @staticmethod
    def label_from_instance(obj):
        return obj.title


class OwnerRightsRequestForm(forms.Form):
    resource = forms.ModelChoiceField(
        label=_("Resource"), queryset=ResourceBase.objects.all(), widget=forms.HiddenInput()
    )
    reason = forms.CharField(
        label=_("Reason"), widget=forms.Textarea, help_text=_("Short reasoning behind the request"), required=True
    )

    class Meta:
        fields = ["reason", "resource"]


class ThesaurusImportForm(forms.Form):
    rdf_file = forms.FileField()


class ContactRoleForm(forms.ModelForm):
    """Form for individual contact role entry (one contact, one role, one order)"""

    contact = forms.ModelChoiceField(
        queryset=get_user_model().objects.exclude(username="AnonymousUser"),
        label=_("User"),
        widget=autocomplete.ModelSelect2(url="autocomplete_profile"),
        required=False,
    )

    role = forms.ChoiceField(
        choices=[(r.role_value, r.label) for r in Roles.get_multivalue_ones()],
        label=_("Role"),
        required=False,
    )

    order = forms.IntegerField(
        label=_("Order"),
        min_value=0,
        required=False,
        help_text=_("Lower numbers appear first"),
    )

    class Meta:
        model = ContactRole
        fields = ["contact", "role", "order"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].label_from_instance = get_user_display_name

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("DELETE"):
            return cleaned_data

        contact = cleaned_data.get("contact")
        role = cleaned_data.get("role")
        order = cleaned_data.get("order")

        field_values = [contact, role, order]
        is_empty = all(value in (None, "") for value in field_values)

        if is_empty:
            if self.instance and self.instance.pk:
                raise forms.ValidationError(
                    _("Existing contact roles must include user, role, and order or be removed."),
                    code="empty_existing_contact_role",
                )
            return cleaned_data

        if not contact:
            self.add_error("contact", _("This field is required."))
        if not role:
            self.add_error("role", _("This field is required."))
        if order in (None, ""):
            self.add_error("order", _("This field is required."))

        return cleaned_data


class ContactRoleInlineFormSet(BaseInlineFormSet):
    """Ensures each contact/role pair is unique within the resource"""

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        seen_contact_role = set()
        seen_role_order = set()
        duplicate_contact_labels = []
        duplicate_order_labels = []
        role_choices = dict(ContactRoleForm.base_fields["role"].choices)

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            contact = form.cleaned_data.get("contact")
            role = form.cleaned_data.get("role")
            if not contact or not role:
                continue

            key_contact_role = (contact.pk, role)
            if key_contact_role in seen_contact_role:
                duplicate_contact_labels.append(f"{get_user_display_name(contact)} / {role_choices.get(role, role)}")
            else:
                seen_contact_role.add(key_contact_role)

            order_value = form.cleaned_data.get("order")
            if order_value in (None, ""):
                continue
            key_role_order = (role, order_value)
            if key_role_order in seen_role_order:
                duplicate_order_labels.append(
                    _("%(role)s (order %(order)s)") % {"role": role_choices.get(role, role), "order": order_value}
                )
            else:
                seen_role_order.add(key_role_order)

        error_messages = []
        if duplicate_contact_labels:
            error_messages.append(
                _("Each user can only be assigned once per role. Please adjust these duplicates: %(duplicates)s")
                % {"duplicates": ", ".join(duplicate_contact_labels)}
            )
        if duplicate_order_labels:
            error_messages.append(
                _("Each role can only use an order value once. Please adjust these duplicates: %(duplicates)s")
                % {"duplicates": ", ".join(duplicate_order_labels)}
            )

        if error_messages:
            raise forms.ValidationError(error_messages)


ContactRoleFormSet = forms.inlineformset_factory(
    ResourceBase,
    ContactRole,
    form=ContactRoleForm,
    formset=ContactRoleInlineFormSet,
    extra=0,
    can_delete=True,
)
