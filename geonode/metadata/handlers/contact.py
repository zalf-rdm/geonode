#########################################################################
#
# Copyright (C) 2024 OSGeo
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
from rest_framework.reverse import reverse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from geonode.base.models import ContactRole
from geonode.metadata.handlers.abstract import MetadataHandler
from geonode.people import Roles
from geonode.resource.manager import resource_manager

logger = logging.getLogger(__name__)

# contact roles names are spread in the code, let's map them here:
ROLE_NAMES_MAP = {
    Roles.OWNER: "owner",  # this is not saved as a contact
    Roles.METADATA_AUTHOR: "author",
    Roles.PROCESSOR: Roles.PROCESSOR.name,
    Roles.PUBLISHER: Roles.PUBLISHER.name,
    Roles.CUSTODIAN: Roles.CUSTODIAN.name,
    Roles.POC: "pointOfContact",
    Roles.DISTRIBUTOR: Roles.DISTRIBUTOR.name,
    Roles.RESOURCE_USER: Roles.RESOURCE_USER.name,
    Roles.RESOURCE_PROVIDER: Roles.RESOURCE_PROVIDER.name,
    Roles.ORIGINATOR: Roles.ORIGINATOR.name,
    Roles.PRINCIPAL_INVESTIGATOR: Roles.PRINCIPAL_INVESTIGATOR.name,
    Roles.DATA_COLLECTOR: Roles.DATA_COLLECTOR.name,
    Roles.DATA_CURATOR: Roles.DATA_CURATOR.name,
    Roles.EDITOR: Roles.EDITOR.name,
    Roles.HOSTING_INSTITUTION: Roles.HOSTING_INSTITUTION.name,
    Roles.OTHER: Roles.OTHER.name,
    Roles.PRODUCER: Roles.PRODUCER.name,
    Roles.PROJECT_LEADER: Roles.PROJECT_LEADER.name,
    Roles.PROJECT_MANAGER: Roles.PROJECT_MANAGER.name,
    Roles.PROJECT_MEMBER: Roles.PROJECT_MEMBER.name,
    Roles.REGISTRATION_AGENCY: Roles.REGISTRATION_AGENCY.name,
    Roles.REGISTRATION_AUTHORITY: Roles.REGISTRATION_AUTHORITY.name,
    Roles.RELATED_PERSON: Roles.RELATED_PERSON.name,
    Roles.RESEARCH_GROUP: Roles.RESEARCH_GROUP.name,
    Roles.RESEARCHER: Roles.RESEARCHER.name,
    Roles.RIGHTS_HOLDER: Roles.RIGHTS_HOLDER.name,
    Roles.SPONSOR: Roles.SPONSOR.name,
    Roles.SUPERVISOR: Roles.SUPERVISOR.name,
    Roles.WORK_PACKAGE_LEADER: Roles.WORK_PACKAGE_LEADER.name,
}

NAMES_ROLE_MAP = {v: k for k, v in ROLE_NAMES_MAP.items()}


class ContactHandler(MetadataHandler):
    """
    Handles role contacts
    """

    def update_schema(self, jsonschema, context, lang=None):
        contacts = {}
        required = []
        for role in Roles:
            rolename = ROLE_NAMES_MAP[role]
            minitems = 1 if role.is_required else 0
            card = f' [{minitems}..{"N" if role.is_multivalue else "1"}]' if settings.DEBUG else ""
            if role.is_required:
                required.append(rolename)

            if role.is_multivalue:
                contact = {
                    "type": "array",
                    "title": self._localize_label(context, lang, role.label) + card,
                    "minItems": minitems,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "title": _("User id"),
                            },
                            "label": {
                                "type": "string",
                                "title": _("User name"),
                            },
                        },
                    },
                    "ui:options": {"geonode-ui:autocomplete": reverse("metadata_autocomplete_users")},
                }
            else:
                contact = {
                    "type": "object",
                    "title": self._localize_label(context, lang, role.label) + card,
                    "properties": {
                        "id": {
                            "type": "string",
                            "title": _("User id"),
                            "ui:widget": "hidden",
                        },
                        "label": {
                            "type": "string",
                            "title": _("User name"),
                        },
                    },
                    "ui:options": {"geonode-ui:autocomplete": reverse("metadata_autocomplete_users")},
                    "required": ["id"] if role.is_required else [],
                }

            contacts[rolename] = contact

            subschema = {
                "type": "object",
                "title": "contacts",
                "properties": contacts,
                "required": required,
                "geonode:required": bool(required),
                "geonode:handler": "contact",
            }

            self._localize_subschema_labels(context, subschema, lang, "contacts")
            self._add_subschema(jsonschema, "contacts", subschema)

        return jsonschema

    def get_jsonschema_instance(self, resource, field_name, context, errors, lang=None):
        def __create_user_entry(user, order=None):
            names = [n for n in (user.first_name, user.last_name) if n]
            if names:
                label = " ".join(names)
            elif getattr(user, "department", None):
                label = user.department
            else:
                label = user.username
            entry = {"id": str(user.id), "label": label}
            if order is not None:
                entry["order"] = order
            return entry

        contacts = {}
        for role in Roles:
            rolename = ROLE_NAMES_MAP[role]
            if role.is_multivalue:
                crs = ContactRole.objects.filter(
                    role=role.role_value, resource=resource
                ).select_related("contact").order_by("order")
                content = [__create_user_entry(cr.contact, cr.order) for cr in crs]
            else:
                crs = ContactRole.objects.filter(
                    role=role.role_value, resource=resource
                ).select_related("contact").order_by("order")
                if not crs and role == Roles.OWNER:
                    content = __create_user_entry(resource.owner)
                else:
                    content = __create_user_entry(crs[0].contact, crs[0].order) if crs else None

            contacts[rolename] = content

        return contacts

    def update_resource(self, resource, field_name, json_instance, context, errors, **kwargs):
        data = json_instance[field_name]
        logger.debug(f"CONTACTS {data}")
        for rolename, users in data.items():
            if rolename == Roles.OWNER.name:
                if not users:
                    logger.warning(f"User not specified for role '{rolename}'")
                    self._set_error(
                        errors,
                        ["contacts", rolename],
                        self.localize_message(
                            context, "metadata_contact_error_missing_role", {"fieldname": field_name, "role": rolename}
                        ),
                    )
                else:
                    try:
                        user = get_user_model().objects.get(pk=users["id"])

                        if user != resource.owner:
                            logger.warning(f"Changing owner from {resource.owner} to {user}")
                            resource_manager.transfer_ownership(resource, user, resource.owner)
                    except get_user_model().DoesNotExist:
                        logger.warning(f"User with id {users['id']} not found for role '{rolename}'")
                        self._set_error(errors, ["contacts", rolename], f"User with id {users['id']} does not exist.")
            else:
                role_value = NAMES_ROLE_MAP[rolename].role_value
                ContactRole.objects.filter(role=role_value, resource=resource).delete()
                for idx, u in enumerate(users):
                    # Always derive order from the array position — the client sends entries
                    # in display order, so idx is always the correct authoritative order value.
                    # Trusting the echoed-back 'order' field would preserve stale values when
                    # the user reorders contacts in the UI.
                    try:
                        user = get_user_model().objects.get(pk=u["id"] if isinstance(u, dict) else u)
                        ContactRole.objects.create(
                            role=role_value, resource=resource, contact=user, order=idx
                        )
                    except get_user_model().DoesNotExist:
                        uid = u.get("id") if isinstance(u, dict) else u
                        logger.warning(f"User with id {uid} not found for role '{rolename}'")
                        self._set_error(errors, ["contacts", rolename], f"User with id {uid} does not exist.")
