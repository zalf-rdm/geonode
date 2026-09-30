#########################################################################
#
# Copyright (C) 2026 Open Source Geospatial Foundation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
#########################################################################

import logging

from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.utils.translation import gettext_lazy as _

from geonode.facets.models import DEFAULT_FACET_PAGE_SIZE, FACET_TYPE_DATE, FacetProvider

logger = logging.getLogger(__name__)


class DateFacetProvider(FacetProvider):
    """Aggregate visible, prefiltered resources into chronological year buckets."""

    @property
    def name(self) -> str:
        return "date"

    def get_info(self, lang="en", **kwargs) -> dict:
        return {
            "name": self.name,
            "filter": "filter{date}",
            "label": _("Date"),
            "type": FACET_TYPE_DATE,
            "hierarchical": False,
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
        if topic_contains:
            logger.warning("Facet %s does not support topic_contains filtering", self.name)

        buckets = (
            queryset.exclude(date__isnull=True)
            .annotate(year=ExtractYear("date"))
            .values("year")
            .annotate(count=Count("pk"))
            .order_by("year")
        )

        if keys:
            valid_years = []
            for key in keys:
                try:
                    valid_years.append(int(key))
                except (TypeError, ValueError):
                    continue
            buckets = buckets.filter(year__in=valid_years)

        count = buckets.count()
        topics = [
            {"key": bucket["year"], "label": str(bucket["year"]), "count": bucket["count"]}
            for bucket in buckets[start:end]
        ]
        return count, topics

    def get_topics(self, keys: list, lang="en", **kwargs) -> list:
        return [{"key": year, "label": str(year)} for year in sorted({int(key) for key in keys if str(key).isdigit()})]

    @classmethod
    def register(cls, registry, **kwargs) -> None:
        registry.register_facet_provider(cls(**kwargs))
