from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0124_geokeyword_geometry"),
    ]

    operations = [
        migrations.AlterField(
            model_name="resourcebase",
            name="abstract_translated",
            field=models.TextField(
                help_text="brief german narrative summary of the content of the resource(s)",
                max_length=6000,
                verbose_name="Abstract (German)",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="data_lineage",
            field=models.TextField(
                blank=True,
                help_text="description of the lineage of the dataset, including its origin and history",
                max_length=6000,
                verbose_name="Data Lineage",
            ),
        ),
    ]
