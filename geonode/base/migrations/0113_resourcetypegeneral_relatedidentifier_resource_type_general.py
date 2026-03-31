from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0112_contactrole_unique_role_order"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResourceTypeGeneral",
            fields=[
                (
                    "label",
                    models.CharField(
                        help_text="DataCite resourceTypeGeneral controlled vocabulary",
                        max_length=255,
                        primary_key=True,
                        serialize=False,
                        unique=True,
                        verbose_name="Label",
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        help_text="Description of the general resource type",
                        max_length=255,
                        verbose_name="Description",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="relatedidentifier",
            name="resource_type_general",
            field=models.ForeignKey(
                blank=True,
                help_text="The general type of the related resource (DataCite controlled vocabulary)",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="base.resourcetypegeneral",
            ),
        ),
    ]
