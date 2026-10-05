from django.contrib.gis.db import models
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0123_alter_resourcebase_abstract_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="geokeyword",
            name="geometry",
            field=models.MultiPolygonField(
                blank=True,
                help_text="Verified boundary used for geographic discovery",
                null=True,
                srid=4326,
            ),
        ),
    ]
