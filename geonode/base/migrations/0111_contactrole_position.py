# Generated manually for issue #324

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0110_remove_resourcebase_date_collected_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactrole",
            name="position",
            field=models.IntegerField(default=0, help_text="Order position for this contact role"),
        ),
        migrations.AlterModelOptions(
            name="contactrole",
            options={"ordering": ["position", "id"]},
        ),
    ]
