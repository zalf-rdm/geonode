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

from django.core.exceptions import ValidationError

from rest_framework.exceptions import ParseError
from dynamic_rest.fields.fields import DynamicRelationField

from geonode.base.models import (
    RelatedIdentifierType,
    RelationType,
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
            RelatedIdentifier.objects.get_or_create(
                related_identifier=data["related_identifier"], related_identifier_type=rit, relation_type=rt
            )[0].save()
            r = RelatedIdentifier.objects.get(
                related_identifier=data["related_identifier"], related_identifier_type=rit, relation_type=rt
            )
        except TypeError:
            raise ParseError(detail="Could not convert related_identifier to internal object ...", code=400)
        return r


class FundingsDynamicRelationField(DynamicRelationField):
    def to_internal_value_single(self, data, serializer):
        try:
            organization = Organization.objects.get(**data["organization"])
            data["organization"] = organization
        except TypeError:
            raise ParseError(detail="Missing funding_organization object in funding ...", code=400)
        try:
            funder = Funding.objects.get_or_create(**data)
        except TypeError:
            raise ParseError(detail="Could not convert funding to internal object ...", code=400)
        return funder[0]


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
