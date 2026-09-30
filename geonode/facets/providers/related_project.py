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

from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from geonode.base.models import RelatedProject
from geonode.facets.models import DEFAULT_FACET_PAGE_SIZE, FACET_TYPE_RELATED_PROJECT, FacetProvider

logger = logging.getLogger(__name__)


class RelatedProjectFacetProvider(FacetProvider):
    """Provide catalogue facets for the projects related to resources."""

    @property
    def name(self) -> str:
        return "related_project"

    def get_info(self, lang="en", **kwargs) -> dict:
        return {
            "name": self.name,
            "filter": "filter{related_projects.pk.in}",
            "label": _("Related project"),
            "type": FACET_TYPE_RELATED_PROJECT,
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
        filters = {"related_projects__in": queryset}
        if topic_contains:
            filters["display_name__icontains"] = topic_contains
        if keys:
            filters["pk__in"] = keys

        projects = (
            RelatedProject.objects.filter(**filters)
            .values("pk", "display_name")
            .annotate(count=Count("related_projects", distinct=True))
            .order_by("-count", "display_name", "pk")
        )
        count = projects.count()
        topics = [
            {
                "key": project["pk"],
                "label": project["display_name"],
                "count": project["count"],
            }
            for project in projects[start:end]
        ]
        logger.info("Found %d facets for %s", count, self.name)
        return count, topics

    def get_topics(self, keys: list, lang="en", **kwargs) -> list:
        return [
            {"key": project["pk"], "label": project["display_name"]}
            for project in RelatedProject.objects.filter(pk__in=keys)
            .values("pk", "display_name")
            .order_by("display_name", "pk")
        ]

    @classmethod
    def register(cls, registry, **kwargs) -> None:
        registry.register_facet_provider(cls(**kwargs))
