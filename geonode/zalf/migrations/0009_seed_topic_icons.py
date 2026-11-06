"""
Give the seeded topics their outline icons (zalf-rdm/geonode#863).

Only touches the ten slugs `0005_seed_topics` created, and only where the admin
has not already chosen an icon, so curated content is never clobbered.

The names must exist in the client's `themes/zalf/utils/TopicIcons.js`, which
owns the icon vocabulary; an unknown name renders no icon rather than breaking
the card.
"""

from django.db import migrations

ICONS = {
    "animals": "paw",
    "atmosphere": "cloud",
    "climate": "sun",
    "forest": "tree",
    "hydrology": "waves",
    "landscape": "mountain",
    "long-term-experiments": "flask",
    "plants": "seedling",
    "soil-profiles": "layers",
    "water": "droplet",
}


def seed_icons(apps, schema_editor):
    Topic = apps.get_model("zalf", "Topic")
    for slug, icon in ICONS.items():
        Topic.objects.filter(slug=slug, icon="").update(icon=icon)


def unseed_icons(apps, schema_editor):
    Topic = apps.get_model("zalf", "Topic")
    for slug, icon in ICONS.items():
        Topic.objects.filter(slug=slug, icon=icon).update(icon="")


class Migration(migrations.Migration):

    dependencies = [("zalf", "0008_topic_icon")]

    operations = [migrations.RunPython(seed_icons, unseed_icons)]
