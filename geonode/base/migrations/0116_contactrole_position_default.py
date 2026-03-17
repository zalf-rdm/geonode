from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0115_merge_20260227_1249"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "UPDATE base_contactrole SET position = 0 WHERE position IS NULL;"
                "ALTER TABLE base_contactrole ALTER COLUMN position SET DEFAULT 0;"
            ),
            reverse_sql=("ALTER TABLE base_contactrole ALTER COLUMN position DROP DEFAULT;"),
        ),
    ]
