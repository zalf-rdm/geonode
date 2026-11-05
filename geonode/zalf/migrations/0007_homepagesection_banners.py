"""
Add the Spotlight Banners homepage section (zalf-rdm/geonode#863).

Commit 09f2524d0 removed the spotlight carousel from the homepage but left the
model, API, CMS tab and CSS in place. The section is restored, so every CMS
content type now has a homepage section that can be ordered and hidden.

It is seeded after Topics — the position the carousel held before it was removed.
"""

from django.db import migrations, models


def seed(apps, schema_editor):
    HomepageSection = apps.get_model("zalf", "HomepageSection")
    if HomepageSection.objects.filter(key="banners").exists():
        return
    # Insert at position 2 (after cases and topics) and push the rest down, so an
    # order the admin has already chosen for the other sections is preserved.
    HomepageSection.objects.filter(order__gte=2).update(order=models.F("order") + 1)
    HomepageSection.objects.create(key="banners", order=2, is_active=True)


def unseed(apps, schema_editor):
    HomepageSection = apps.get_model("zalf", "HomepageSection")
    HomepageSection.objects.filter(key="banners").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("zalf", "0006_homepagesection"),
    ]

    operations = [
        migrations.AlterField(
            model_name="homepagesection",
            name="key",
            field=models.CharField(
                choices=[
                    ("cases", "Highlighted Datasets"),
                    ("topics", "Browse by Topic"),
                    ("banners", "Spotlight Banners"),
                    ("trainings", "Training Resources"),
                ],
                max_length=32,
                unique=True,
            ),
        ),
        migrations.RunPython(seed, unseed),
    ]
