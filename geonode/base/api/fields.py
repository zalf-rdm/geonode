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
import json

from django.core.exceptions import ValidationError, MultipleObjectsReturned

from rest_framework.exceptions import ParseError
from dynamic_rest.fields.fields import DynamicRelationField

from geonode.base.models import (
    RelatedIdentifierType,
    RelationType,
    ResourceTypeGeneral,
    RelatedIdentifier,
    Organization,
    Funding,
    HierarchicalKeyword,
)


class RelatedIdentifierDynamicRelationField(DynamicRelationField):
    def to_internal_value_single(self, data, serializer):
        try:
            rit = RelatedIdentifierType.objects.get(**data["related_identifier_type"])
            rt = RelationType.objects.get(**data["relation_type"])
            rtg = None
            if data.get("resource_type_general"):
                rtg = ResourceTypeGeneral.objects.get(**data["resource_type_general"])
            lookup = {
                "related_identifier": data["related_identifier"],
                "related_identifier_type": rit,
                "relation_type": rt,
                "resource_type_general": rtg,
            }
            r = RelatedIdentifier.objects.filter(**lookup).first()
            if not r:
                r = RelatedIdentifier(**lookup)
        except TypeError:
            raise ParseError(detail="Could not convert related_identifier to internal object ...", code=400)
        return r


class FundingsDynamicRelationField(DynamicRelationField):
    """Generic nested get-or-create handler for fundings payload.

    Supports payloads with either:
    - organization: {...}
    - funding_organization: {...}

    and resolves/creates Organization first, then Funding.
    """

    nested_relations = {
        "organization": {
            "model": Organization,
            "aliases": ("organization", "funding_organization"),
            # Prefer stable identifiers first, then progressively weaker matches.
            "lookup_order": (("ror",), ("organization", "abbreviation"), ("organization",)),
            "required": True,
        }
    }

    @staticmethod
    def _clean_dict(data):
        return {k: v for k, v in data.items() if v not in (None, "")}

    def _get_alias_value(self, data, aliases):
        for alias in aliases:
            if alias in data:
                return alias, data[alias]
        return None, None

    def _resolve_nested_instance(self, rel_name, rel_cfg, rel_raw):
        model = rel_cfg["model"]

        if isinstance(rel_raw, model):
            return rel_raw

        if isinstance(rel_raw, (int, str)):
            rel_raw_id = rel_raw
            if isinstance(rel_raw, str):
                rel_raw_id = rel_raw.strip()
                if not rel_raw_id.isdigit():
                    rel_raw_id = None
            try:
                if rel_raw_id is not None:
                    return model.objects.get(pk=int(rel_raw_id))
            except model.DoesNotExist:
                raise ParseError(detail=f"Object with id={rel_raw} for '{rel_name}' not found", code=400)

        if not isinstance(rel_raw, dict):
            raise ParseError(
                detail=f"Invalid object for '{rel_name}' in payload ...",
                code=400,
            )

        rel_data = dict(rel_raw)

        # Allow direct reference by id when clients already have it.
        if rel_data.get("id"):
            try:
                return model.objects.get(pk=rel_data["id"])
            except (ValueError, TypeError, model.DoesNotExist):
                raise ParseError(detail=f"Object with id={rel_data['id']} for '{rel_name}' not found", code=400)

        rel_data = self._clean_dict(rel_data)
        if not rel_data:
            raise ParseError(
                detail=f"Missing '{rel_name}' object in payload ...",
                code=400,
            )

        # Try deterministic lookup chains first; create only if no match exists.
        for keys in rel_cfg.get("lookup_order", ()):
            if all(rel_data.get(k) not in (None, "") for k in keys):
                lookup = {k: rel_data[k] for k in keys}
                instance = model.objects.filter(**lookup).first()
                if instance:
                    return instance

                defaults = {k: v for k, v in rel_data.items() if k not in lookup}
                try:
                    return model.objects.get_or_create(**lookup, defaults=defaults)[0]
                except MultipleObjectsReturned:
                    return model.objects.filter(**lookup).first()

        try:
            instance, _ = model.objects.get_or_create(**rel_data)
            return instance
        except MultipleObjectsReturned:
            return model.objects.filter(**rel_data).first()

    def to_internal_value_single(self, data, serializer):
        try:
            if isinstance(data, str):
                data = json.loads(data)
        except ValueError:
            return super().to_internal_value_single(data, serializer)

        if not isinstance(data, dict):
            return super().to_internal_value_single(data, serializer)

        payload = dict(data)

        # Reuse existing funding if id is explicitly provided.
        funding_id = payload.get("id")
        if funding_id:
            try:
                return Funding.objects.get(pk=funding_id)
            except (ValueError, TypeError, Funding.DoesNotExist):
                raise ParseError(detail=f"Funding with id={funding_id} not found", code=400)

        try:
            for rel_name, rel_cfg in self.nested_relations.items():
                alias, rel_raw = self._get_alias_value(payload, rel_cfg.get("aliases", (rel_name,)))
                if rel_raw is None:
                    if rel_cfg.get("required", False):
                        raise ParseError(
                            detail=f"Missing {rel_name} object in funding ...",
                            code=400,
                        )
                    continue

                payload[rel_name] = self._resolve_nested_instance(rel_name, rel_cfg, rel_raw)

                # Remove alias key if canonical key differs.
                if alias and alias != rel_name:
                    payload.pop(alias, None)

            payload = self._clean_dict(payload)
            try:
                funder, _ = Funding.objects.get_or_create(**payload)
            except MultipleObjectsReturned:
                funder = Funding.objects.filter(**payload).first()
        except TypeError:
            raise ParseError(detail="Could not convert funding to internal object ...", code=400)
        except ValidationError:
            raise ParseError(detail="Invalid funding payload ...", code=400)

        return funder


class KeywordsDynamicRelationField(DynamicRelationField):
    def to_internal_value_single(self, data, serializer):
        """Overwrite of DynamicRelationField implementation to handle complex data structure initialization

        Args:
            data (Union[str, Dict]}): serialized or deserialized data from http calls (POST, GET ...),
                                      if content-type application/json is used, data shows up as dict
            serializer (DynamicModelSerializer): Serializer for the given data

        Raises:
            ValidationError: raised when requested data does not exist

            django.db.models.QuerySet: return QuerySet object of the request or set data
        """
        try:
            if isinstance(data, str):
                data = json.loads(data)
        except ValueError:
            return super().to_internal_value_single(data, serializer)

        if not isinstance(data, dict):
            return super().to_internal_value_single(data, serializer)

        def __set_full_keyword__(d):
            if "name" not in d:
                raise ValidationError('No "name" object found for given keyword ...')
            if "slug" not in d:
                d["slug"] = d["name"]
            if "depth" not in d:
                d["depth"] = 1
            if "path" not in d:
                d["path"] = d["name"]
            return d

        data = __set_full_keyword__(data)
        keyword = HierarchicalKeyword.objects.filter(name=data["name"]).first()
        if keyword is None:
            keyword = HierarchicalKeyword.objects.create(
                name=data["name"], slug=data["slug"], depth=data["depth"], path=data["path"]
            )
        keyword.save()
        return keyword


class ComplexDynamicRelationField(DynamicRelationField):
    def to_internal_value_single(self, data, serializer):
        """Overwrite of DynamicRelationField implementation to handle complex data structure initialization

        Args:
            data (Union[str, Dict]}): serialized or deserialized data from http calls (POST, GET ...),
                                      if content-type application/json is used, data shows up as dict
            serializer (DynamicModelSerializer): Serializer for the given data

        Raises:
            ValidationError: raised when requested data does not exist

            django.db.models.QuerySet: return QuerySet object of the request or set data
        """
        related_model = serializer.Meta.model
        try:
            if isinstance(data, str):
                data = json.loads(data)
        except ValueError:
            return super().to_internal_value_single(data, serializer)

        if isinstance(data, dict):
            try:
                if hasattr(serializer, "many") and serializer.many is True:
                    return [serializer.get_model().objects.get(**d) for d in data]
                return serializer.get_model().objects.get(**data)
            except related_model.DoesNotExist:
                raise ValidationError(
                    "Invalid value for '%s': %s object with ID=%s not found"
                    % (self.field_name, related_model.__name__, data)
                )
        else:
            return super().to_internal_value_single(data, serializer)
