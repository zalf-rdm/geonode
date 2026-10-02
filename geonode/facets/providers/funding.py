#########################################################################
#
# Copyright (C) 2026 Leibniz Centre for Agricultural Landscape Research
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#########################################################################

import logging

from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _

from geonode.base.models import Organization
from geonode.facets.models import DEFAULT_FACET_PAGE_SIZE, FACET_TYPE_FUNDING, FacetProvider

logger = logging.getLogger(__name__)


class FundingFacetProvider(FacetProvider):
    """Provide catalogue facets for organizations funding resources."""

    @property
    def name(self) -> str:
        return "funding"

    def get_info(self, lang="en", **kwargs) -> dict:
        return {
            "name": self.name,
            "filter": "filter{fundings.organization.pk.in}",
            "label": _("Fundings"),
            "type": FACET_TYPE_FUNDING,
        }

    def get_facet_items(
        self,
        queryset,
        start: int = 0,
        end: int = DEFAULT_FACET_PAGE_SIZE,
        lang="en",
        topic_contains: str = None,
        keys: set = {},
        **kwargs,
    ) -> (int, list):
        filters = {"funding__resourcebase__in": queryset}
        if topic_contains:
            filters["organization__icontains"] = topic_contains
        if keys:
            filters["pk__in"] = keys

        organizations = (
            Organization.objects.filter(**filters)
            .exclude(Q(organization__isnull=True) | Q(organization=""))
            .values("pk", "organization")
            .annotate(count=Count("funding__resourcebase", distinct=True))
            .order_by("-count", "organization", "pk")
        )
        count = organizations.count()
        topics = [
            {
                "key": organization["pk"],
                "label": organization["organization"],
                "count": organization["count"],
            }
            for organization in organizations[start:end]
        ]
        logger.info("Found %d facets for %s", count, self.name)
        return count, topics

    def get_topics(self, keys: list, lang="en", **kwargs) -> list:
        return [
            {"key": organization["pk"], "label": organization["organization"]}
            for organization in Organization.objects.filter(pk__in=keys)
            .exclude(Q(organization__isnull=True) | Q(organization=""))
            .values("pk", "organization")
            .order_by("organization", "pk")
        ]

    @classmethod
    def register(cls, registry, **kwargs) -> None:
        registry.register_facet_provider(cls(**kwargs))
