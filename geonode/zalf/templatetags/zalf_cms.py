"""Template tags for the ZALF CMS (zalf-rdm/geonode#863)."""

from django.template import Library
from django.utils import translation

from geonode.zalf.models import TOPIC_TRANSLATED_LANGUAGES, navbar_topic_rows

register = Library()


@register.simple_tag
def zalf_navbar_topic_columns(max_columns=2, max_per_column=5):
    """
    Active navbar topics as balanced lists of ``{"name", "href"}``, localized to
    the active language.

    Pre-split in Python because Django templates cannot do ceil division. The
    number of columns grows with the list instead of being fixed at two: the
    dropdown's `is-wide` rule is a 520px two-track grid, so forcing two columns
    on a short list left the right-hand half empty. `max_per_column=5` reproduces
    the 5/5 split of the markup this replaced for the ten seeded topics, keeps
    anything up to five topics in a single column, and balances the rest.
    """
    code = (translation.get_language() or "en").split("-")[0].lower()
    key = f"name_{code}" if code in TOPIC_TRANSLATED_LANGUAGES else None
    topics = [
        {
            "name": ((row.get(key) or "").strip() if key else "") or row["name"],
            "href": row["href"],
        }
        for row in navbar_topic_rows()
    ]
    if not topics or max_columns < 1 or max_per_column < 1:
        return []
    column_count = min(max_columns, -(-len(topics) // max_per_column)) or 1
    size = -(-len(topics) // column_count)  # ceil division
    return [topics[i : i + size] for i in range(0, len(topics), size)]
