"""
Homepage section order (zalf-rdm/geonode#863).

Seeds one row per CMS-driven homepage section in the order they render today,
so applying this migration changes nothing visually.
"""

from django.db import migrations, models

# Must match HOMEPAGE_SECTION_CHOICES in geonode/zalf/models.py, in the order
# the sections were hardcoded in Homepage.jsx.
SECTIONS = ["cases", "topics", "trainings"]


def seed(apps, schema_editor):
    HomepageSection = apps.get_model("zalf", "HomepageSection")
    for order, key in enumerate(SECTIONS):
        # get_or_create so a re-run (or a partially seeded DB) is harmless and
        # an admin's chosen order is never overwritten.
        HomepageSection.objects.get_or_create(key=key, defaults={"order": order, "is_active": True})


def unseed(apps, schema_editor):
    HomepageSection = apps.get_model("zalf", "HomepageSection")
    HomepageSection.objects.filter(key__in=SECTIONS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("zalf", "0005_seed_topics"),
    ]

    operations = [
        migrations.CreateModel(
            name="HomepageSection",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "key",
                    models.CharField(
                        choices=[
                            ("cases", "Highlighted Datasets"),
                            ("topics", "Browse by Topic"),
                            ("trainings", "Training Resources"),
                        ],
                        max_length=32,
                        unique=True,
                    ),
                ),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("order", "id"),
            },
        ),
        migrations.RunPython(seed, unseed),
    ]
