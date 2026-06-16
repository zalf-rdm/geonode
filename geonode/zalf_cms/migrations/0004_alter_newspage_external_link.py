# Generated manually for internal and external editorial links.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("zalf_cms", "0003_newspage_external_link_newspage_is_featured"),
    ]

    operations = [
        migrations.AlterField(
            model_name="newspage",
            name="external_link",
            field=models.CharField(
                blank=True,
                help_text="Supports internal paths like /catalogue/#/... and external URLs.",
                max_length=500,
            ),
        ),
    ]
