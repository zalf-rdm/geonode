# Generated manually for issue #324
# Originally added a 'position' field to ContactRole, but the upstream
# 0111_alter_contactrole_options_contactrole_order migration added an
# 'order' field instead.  This migration is now a no-op; the merge
# migration 0115 keeps the dependency graph intact.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0110_remove_resourcebase_date_collected_and_more"),
    ]

    operations = []
