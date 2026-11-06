"""
Seed the ten topics that used to be hardcoded (zalf-rdm/geonode#863).

Every value here is copied verbatim from the previous sources, so applying this
migration is a visual no-op: the same 10 navbar entries, the same 8 homepage
cards, the same labels in all five locales and the same `?q=` URLs.

Labels come from the `zalfTheme.topic.*` tables in the client's
gn-translations/data.*.json (all five locales carried a complete 10-entry set).
Converting a topic from a free-text term to real facet filters is then a content
task in the CMS rather than a code change — which is the point of the issue.
"""

from django.db import migrations

# (slug, order, search_term, en, de, fr, es, it, show_on_homepage)
#
# show_on_homepage reproduces the pre-existing drift on purpose: the navbar
# listed 10 topics and the homepage grid only 8.
TOPICS = [
    ("animals", 0, "Animals", "Animals", "Tiere", "Animaux", "Animales", "Animali", True),
    ("atmosphere", 1, "Atmosphere", "Atmosphere", "Atmosphäre", "Atmosphère", "Atmósfera", "Atmosfera", True),
    ("climate", 2, "Climate", "Climate", "Klima", "Climat", "Clima", "Clima", True),
    ("forest", 3, "Forest", "Forest", "Wald", "Forêt", "Bosque", "Foresta", True),
    ("hydrology", 4, "Hydrology", "Hydrology", "Hydrologie", "Hydrologie", "Hidrología", "Idrologia", True),
    ("landscape", 5, "Landscape", "Landscape", "Landschaft", "Paysage", "Paisaje", "Paesaggio", True),
    # The search term stays "Long Term Field Experiment" — that is what the
    # catalogue matches; only the label was ever renamed.
    (
        "long-term-experiments",
        6,
        "Long Term Field Experiment",
        "Long Term Experiments (LTE)",
        "Dauerfeldversuche (LTE)",
        "Expériences de longue durée (LTE)",
        "Experimentos de larga duración (LTE)",
        "Esperimenti di lunga durata (LTE)",
        False,
    ),
    ("plants", 7, "Plants", "Plants", "Pflanzen", "Plantes", "Plantas", "Piante", True),
    (
        "soil-profiles",
        8,
        "Soil Profiles",
        "Soil Profiles",
        "Bodenprofile",
        "Profils de sol",
        "Perfiles de suelo",
        "Profili del suolo",
        True,
    ),
    ("water", 9, "Water", "Water", "Wasser", "Eau", "Agua", "Acqua", False),
]


def seed(apps, schema_editor):
    Topic = apps.get_model("zalf", "Topic")
    # Idempotent: never clobber content an admin has already curated.
    if Topic.objects.exists():
        return
    # Slugs are set explicitly: apps.get_model() returns a historical model with
    # no custom save(), and bulk_create skips save() anyway, so the auto-slug
    # override does not run here.
    Topic.objects.bulk_create(
        [
            Topic(
                slug=slug,
                order=order,
                search_term=term,
                name=en,
                name_de=de,
                name_fr=fr,
                name_es=es,
                name_it=it,
                filters=[],
                show_in_navbar=True,
                show_on_homepage=on_homepage,
                is_active=True,
            )
            for slug, order, term, en, de, fr, es, it, on_homepage in TOPICS
        ]
    )


def unseed(apps, schema_editor):
    Topic = apps.get_model("zalf", "Topic")
    Topic.objects.filter(slug__in=[row[0] for row in TOPICS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("zalf", "0004_topic"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
