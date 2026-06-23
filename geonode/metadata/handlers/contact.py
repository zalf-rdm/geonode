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
    Handles role contacts.

    Schema structure:
      contacts: {
        owner: { id, label }                          -- separate, single-value
        contact_roles: [                               -- dynamic array
          { role: "author", users: [ {id, label}, ... ] },
          { role: "pointOfContact", users: [ ... ] },
          ...
        ]
      }
    Only populated roles appear in contact_roles.
    Required roles are always present and cannot be removed (minItems enforced).
    """

    def update_schema(self, jsonschema, context, lang=None):
        # Build the oneOf list for role selection (all roles except owner)
        role_choices = []
        for role in Roles:
            if role == Roles.OWNER:
                continue
            rolename = ROLE_NAMES_MAP[role]
            role_choices.append(
                {
                    "const": rolename,
                    "title": self._localize_label(context, lang, role.label),
                }
            )

        # Owner — separate single-value field
        owner_schema = {
            "type": "object",
            "title": self._localize_label(context, lang, Roles.OWNER.label),
            "properties": {
                "id": {"type": "string", "title": _("User id"), "ui:widget": "hidden"},
                "label": {"type": "string", "title": _("User name")},
            },
            "required": ["id"],
            "ui:options": {"geonode-ui:autocomplete": reverse("metadata_autocomplete_users")},
        }

        # contact_roles — dynamic array of { role, users }
        contact_roles_schema = {
            "type": "array",
            "title": _("Contact Roles"),
            "items": {
                "type": "object",
                "title": _("Role Entry"),
                "properties": {
                    "role": {
                        "type": "string",
                        "title": _("Role"),
                        "oneOf": role_choices,
                        "ui:options": {
                            "geonode-ui:uniqueInArray": {
                                "arrayPath": "contacts.contact_roles",
                                "valueProp": "role",
                            },
                        },
                    },
                    "users": {
                        "type": "array",
                        "title": _("Users"),
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "title": _("User id")},
                                "label": {"type": "string", "title": _("User name")},
                            },
                        },
                        "ui:options": {"geonode-ui:autocomplete": reverse("metadata_autocomplete_users")},
                    },
                },
                "required": ["role", "users"],
            },
        }

        subschema = {
            "type": "object",
            "title": _("Contacts"),
            "properties": {
                "owner": owner_schema,
                "contact_roles": contact_roles_schema,
            },
            "required": ["owner"],
            "geonode:required": True,
            "geonode:handler": "contact",
        }

        self._localize_subschema_labels(context, subschema, lang, "contacts")
        self._add_subschema(jsonschema, "contacts", subschema)

        return jsonschema

    def get_jsonschema_instance(self, resource, field_name, context, errors, lang=None):
        def __create_user_entry(user):
            names = [n for n in (user.first_name, user.last_name) if n]
            if names:
                label = " ".join(names)
            elif getattr(user, "department", None):
                label = user.department
            else:
                label = user.username
            return {"id": str(user.id), "label": label}

        # Owner
        owner = __create_user_entry(resource.owner)

        # All other roles — only emit roles that have at least one contact,
        # plus always include required roles (even if empty)
        contact_roles = []
        required_rolenames = set()
        for role in Roles:
            if role == Roles.OWNER:
                continue
            rolename = ROLE_NAMES_MAP[role]
            if role.is_required:
                required_rolenames.add(rolename)
            crs = (
                ContactRole.objects.filter(role=role.role_value, resource=resource)
                .select_related("contact")
                .order_by("order")
            )
            users = [__create_user_entry(cr.contact) for cr in crs]
            if users or role.is_required:
                contact_roles.append({"role": rolename, "users": users})

        return {"owner": owner, "contact_roles": contact_roles}

    def update_resource(self, resource, field_name, json_instance, context, errors, **kwargs):
        data = json_instance.get(field_name, {})
        logger.debug(f"CONTACTS {data}")

        # Handle owner
        owner_data = data.get("owner")
        if not owner_data:
            logger.warning("User not specified for role 'owner'")
            self._set_error(
                errors,
                ["contacts", "owner"],
                self.localize_message(
                    context, "metadata_contact_error_missing_role", {"fieldname": field_name, "role": "owner"}
                ),
            )
        else:
            try:
                user = get_user_model().objects.get(pk=owner_data["id"])
                if user != resource.owner:
                    logger.warning(f"Changing owner from {resource.owner} to {user}")
                    resource_manager.transfer_ownership(resource, user, resource.owner)
            except get_user_model().DoesNotExist:
                logger.warning(f"User with id {owner_data['id']} not found for role 'owner'")
                self._set_error(errors, ["contacts", "owner"], f"User with id {owner_data['id']} does not exist.")

        # Handle contact_roles array
        contact_roles = data.get("contact_roles", [])

        # Deduplicate: if the same role appears multiple times, merge users
        merged = {}
        for entry in contact_roles:
            rolename = entry.get("role")
            if not rolename or rolename not in NAMES_ROLE_MAP:
                logger.warning(f"Unknown contact role '{rolename}', skipping")
                continue
            if rolename in merged:
                # Merge users from duplicate role entry (append, skip duplicates)
                existing_ids = {u["id"] for u in merged[rolename] if isinstance(u, dict)}
                for u in entry.get("users", []):
                    uid = u["id"] if isinstance(u, dict) else u
                    if uid not in existing_ids:
                        merged[rolename].append(u)
                        existing_ids.add(uid)
            else:
                merged[rolename] = list(entry.get("users", []))

        # Collect all roles mentioned in payload to know which to clear
        roles_in_payload = set(merged.keys())
        for rolename, users in merged.items():

            role_enum = NAMES_ROLE_MAP[rolename]
            role_value = role_enum.role_value

            # Delete existing and recreate in order
            ContactRole.objects.filter(role=role_value, resource=resource).delete()
            for idx, u in enumerate(users):
                try:
                    uid = u["id"] if isinstance(u, dict) else u
                    user = get_user_model().objects.get(pk=uid)
                    ContactRole.objects.create(role=role_value, resource=resource, contact=user, order=idx)
                except get_user_model().DoesNotExist:
                    uid = u.get("id") if isinstance(u, dict) else u
                    logger.warning(f"User with id {uid} not found for role '{rolename}'")
                    self._set_error(errors, ["contacts", rolename], f"User with id {uid} does not exist.")

        # Clear roles that are NOT in payload (they were removed by the user)
        for role in Roles:
            if role == Roles.OWNER:
                continue
            rolename = ROLE_NAMES_MAP[role]
            if rolename not in roles_in_payload:
                ContactRole.objects.filter(role=role.role_value, resource=resource).delete()
