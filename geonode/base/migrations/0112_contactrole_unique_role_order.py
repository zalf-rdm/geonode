from django.db import migrations, models


def ensure_unique_role_orders(apps, schema_editor):
    ContactRole = apps.get_model("base", "ContactRole")

    distinct_pairs = ContactRole.objects.values_list("resource_id", "role").distinct()

    for resource_id, role in distinct_pairs:
        entries = list(
            ContactRole.objects.filter(resource_id=resource_id, role=role).order_by("order", "id")
        )
        used_orders = set()
        next_candidate = 0

        for entry in entries:
            order_value = entry.order
            if order_value is None or order_value in used_orders:
                while next_candidate in used_orders:
                    next_candidate += 1
                entry.order = next_candidate
                entry.save(update_fields=["order"])
                used_orders.add(entry.order)
                next_candidate += 1
            else:
                used_orders.add(order_value)
                if order_value >= next_candidate:
                    next_candidate = order_value + 1


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0111_alter_contactrole_options_contactrole_order"),
    ]

    operations = [
        migrations.RunPython(ensure_unique_role_orders, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="contactrole",
            constraint=models.UniqueConstraint(
                fields=("resource", "role", "order"),
                name="contactrole_unique_role_order",
            ),
        ),
    ]
