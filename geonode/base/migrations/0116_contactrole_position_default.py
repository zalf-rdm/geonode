from django.db import migrations


class Migration(migrations.Migration):
    """
    Originally set a default for the 'position' column on base_contactrole.
    The 'position' field was superseded by 'order' (added in
    0111_alter_contactrole_options_contactrole_order), so this migration is
    now a no-op.
    """

    dependencies = [
        ("base", "0115_merge_20260227_1249"),
    ]

    operations = []
