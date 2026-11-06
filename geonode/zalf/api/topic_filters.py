"""
Validation for Topic filter specs (zalf-rdm/geonode#863).

A spec is a list of rows::

    [{"field": "category",
      "key": "filter{category.identifier.in}",
      "values": ["farming", "soil"],
      "labels": ["Farming", "Soil"]}]

Rows AND together (distinct query keys); the `values` within a row OR together,
because dynamic-rest collects repeated `...in` params into a list.

The allowlist is the **facets registry**, not ResourceBaseSerializer.Meta.fields.
dynamic-rest resolves a dotted filter path by walking nested serializers
(FilterNode.generate_query_key), so Meta.fields alone cannot tell you whether
`category.identifier` is reachable — and re-implementing that walk would both
duplicate third-party internals and still admit paths nobody means to expose,
such as filter{owner.email.icontains}. The facets registry is the vocabulary the
catalogue's own filter sidebar consumes, which is exactly the vetted set wanted
here.

This module deliberately has no DRF dependency, so the model's clean(), the
serializers, the template tag and the tests can all import it.
"""

import re

from django.core.exceptions import ValidationError

from geonode.facets.models import facet_registry

MAX_ROWS = 10
MAX_VALUES_PER_ROW = 20
MAX_VALUE_LENGTH = 200

FILTER_KEY_RE = re.compile(r"^-?filter\{[A-Za-z0-9_.]+\}$")

# Legitimate keys that no provider's get_info() advertises. `subtype.in` is only
# published on the resourcetype provider's *topics* (facets/providers/baseinfo.py).
EXTRA_FILTER_KEYS = {"filter{subtype.in}": "resourcetype"}

# Facet filters deliberately not offered for topics. The CMS editor hides these
# too (TopicEditor.jsx), but the API rejects them regardless so a hand-crafted
# request cannot store one.
UNSUPPORTED_FILTER_KEYS = {
    # Advertises filter{date} but yields year buckets, while ResourceBase.date is
    # a DateTimeField — a bare filter{date}=2019 is an exact datetime match that
    # can never hit. A range is also a different UI shape (two bounds, not a
    # value picker).
    "filter{date}",
    # A yes/no flag on a curated homepage slot, not a subject dimension: a topic
    # called "Featured" would duplicate the Highlighted Datasets section.
    "filter{featured}",
    # Dropped on request: the catalogue's region vocabulary is geographic rather
    # than thematic, so it does not make a useful topic.
    "filter{regions.code.in}",
    # Broken in this fork, so a topic must not be able to generate it.
    # ResourceBaseSerializer declares `author` with source="metadata_author"
    # (serializers.py:691), but ResourceBase.metadata_author is a Python
    # property over the contacts/ContactRole relation, not a column — so
    # dynamic-rest cannot build an ORM path and the request dies with
    # "metadata_author is not a valid field for ResourceBase" (HTTP 500).
    # AuthorFacetProvider advertises the key regardless, which is why the
    # catalogue's own Authors sidebar facet is affected too; that is a
    # pre-existing bug tracked separately. Use `owner` instead, which is a real
    # FK and filters correctly.
    "filter{author.pk.in}",
}

# TKeywordsFilter (geonode/base/api/filters.py) pops filter{tkeywords} before
# dynamic-rest sees it and feeds the values straight to `tkeywords__id=`, so only
# numeric ThesaurusKeyword ids work and no dotted lookups are supported.
#
# Note this key is *not* in EXTRA_FILTER_KEYS: ThesaurusFacetProvider registers
# one provider per Thesaurus row, so filter{tkeywords} is advertised only on an
# instance that actually has thesauri loaded. Leaving it registry-driven keeps
# the server and the CMS editor in step — both read the same registry, so a field
# the editor cannot offer is also a field the API will not accept. The trade-off
# is that thesaurus ids are database-specific and do not survive being copied
# between environments; prefer category/keyword/region for durable topics.
NUMERIC_ONLY_FILTER_KEYS = {"filter{tkeywords}"}


def facet_filter_keys():
    """
    ``{canonical filter param -> facet name}`` for every registered provider.

    Called per validation, never at import time: the registry loads lazily and
    touches the DB (the thesaurus providers query Thesaurus).
    """
    keys = dict(EXTRA_FILTER_KEYS)
    for provider in facet_registry.get_providers():
        info = provider.get_info(lang="en") or {}
        key = info.get("filter")
        if key:
            keys[key] = info.get("name")
    return keys


def validate_filter_spec(value):
    """
    Normalise and validate a filter spec, returning the cleaned list.

    Raises django.core.exceptions.ValidationError.
    """
    if value in (None, "", []):
        return []
    if not isinstance(value, list):
        raise ValidationError("filters must be a list of filter rows.")
    if len(value) > MAX_ROWS:
        raise ValidationError(f"At most {MAX_ROWS} filters per topic.")

    allowed = facet_filter_keys()
    cleaned = []
    seen = set()

    for index, row in enumerate(value):
        where = f"filters[{index}]"
        if not isinstance(row, dict):
            raise ValidationError(f"{where} must be an object.")

        key = (row.get("key") or "").strip()
        if not FILTER_KEY_RE.match(key):
            raise ValidationError(f"{where}.key is not a filter parameter: {key!r}")
        if key in UNSUPPORTED_FILTER_KEYS:
            raise ValidationError(f"{where}.key {key!r} is a range filter and is not supported for topics.")
        if key not in allowed:
            raise ValidationError(f"{where}.key {key!r} is not a filter advertised by any registered facet.")
        if key in seen:
            raise ValidationError(f"{where}.key {key!r} is used more than once; combine the values instead.")
        seen.add(key)

        values = row.get("values") or []
        if not isinstance(values, list) or not values:
            raise ValidationError(f"{where}.values must be a non-empty list.")
        if len(values) > MAX_VALUES_PER_ROW:
            raise ValidationError(f"{where} has more than {MAX_VALUES_PER_ROW} values.")

        normalised = []
        for raw in values:
            # bool before int: isinstance(True, int) is True in Python.
            if raw is None or isinstance(raw, bool) or isinstance(raw, (list, dict)):
                raise ValidationError(f"{where}.values must be strings or numbers.")
            text = str(raw).strip()
            if not text or len(text) > MAX_VALUE_LENGTH:
                raise ValidationError(f"{where}.values has an empty or over-long value.")
            if key in NUMERIC_ONLY_FILTER_KEYS and not text.isdigit():
                raise ValidationError(f"{where}.values must be numeric ThesaurusKeyword ids for {key!r}.")
            if text not in normalised:
                normalised.append(text)

        cleaned.append(
            {
                # Always derived from the validated key, never taken from the
                # request: `field` is provenance for the editor, and a value that
                # disagreed with `key` would be actively misleading.
                "field": allowed[key],
                "key": key,
                "values": normalised,
                # Advisory display cache for the CMS list only — never rendered
                # publicly, so it is capped rather than trusted.
                "labels": [str(label)[:MAX_VALUE_LENGTH] for label in (row.get("labels") or [])][:MAX_VALUES_PER_ROW],
            }
        )

    return cleaned
