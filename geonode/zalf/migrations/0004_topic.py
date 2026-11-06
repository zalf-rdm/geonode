import django.db.models.deletion  # noqa: F401
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("zalf", "0003_training_extra_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Topic",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text="English / default label.", max_length=120)),
                ("name_de", models.CharField(blank=True, default="", max_length=120)),
                ("name_fr", models.CharField(blank=True, default="", max_length=120)),
                ("name_es", models.CharField(blank=True, default="", max_length=120)),
                ("name_it", models.CharField(blank=True, default="", max_length=120)),
                ("slug", models.SlugField(blank=True, unique=True)),
                ("search_term", models.CharField(blank=True, default="", max_length=200)),
                ("filters", models.JSONField(blank=True, default=list)),
                ("image", models.ImageField(blank=True, null=True, upload_to="cms/topics/")),
                ("show_in_navbar", models.BooleanField(default=True)),
                ("show_on_homepage", models.BooleanField(default=True)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("order", "id"),
            },
        ),
    ]
