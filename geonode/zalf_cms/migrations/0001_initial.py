# Generated manually for the ZALF Wagtail CMS app.

from django.db import migrations, models
import django.db.models.deletion
import wagtail.blocks
import wagtail.fields
import wagtail.images.blocks


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("wagtailcore", "0094_alter_page_locale"),
        ("wagtailimages", "0027_image_description"),
    ]

    operations = [
        migrations.CreateModel(
            name="Banner",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("subtitle", models.CharField(blank=True, max_length=255)),
                ("link", models.URLField(blank=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="wagtailimages.image",
                    ),
                ),
            ],
            options={
                "ordering": ("order", "title"),
            },
        ),
        migrations.CreateModel(
            name="HighlightCase",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=160)),
                ("subtitle", models.CharField(blank=True, max_length=255)),
                ("description", models.TextField(blank=True)),
                ("link", models.URLField(blank=True)),
                ("button_text", models.CharField(default="Explore Now", max_length=80)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="wagtailimages.image",
                    ),
                ),
            ],
            options={
                "ordering": ("order", "title"),
            },
        ),
        migrations.CreateModel(
            name="NewsPage",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                ("subtitle", models.CharField(blank=True, max_length=255)),
                ("summary", models.TextField(blank=True)),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [("heading", 0), ("paragraph", 1), ("image", 2), ("quote", 3)],
                        blank=True,
                        block_lookup={
                            0: ("wagtail.blocks.CharBlock", (), {"form_classname": "title", "icon": "title"}),
                            1: (
                                "wagtail.blocks.RichTextBlock",
                                (),
                                {
                                    "features": [
                                        "h2",
                                        "h3",
                                        "bold",
                                        "italic",
                                        "ol",
                                        "ul",
                                        "link",
                                        "document-link",
                                        "image",
                                    ],
                                    "icon": "pilcrow",
                                },
                            ),
                            2: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            3: ("wagtail.blocks.BlockQuoteBlock", (), {}),
                        },
                    ),
                ),
                ("published_at", models.DateField(blank=True, null=True)),
                ("tags", models.CharField(blank=True, help_text="Comma-separated tags for API consumers.", max_length=255)),
                (
                    "hero_image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="wagtailimages.image",
                    ),
                ),
            ],
            options={
                "verbose_name": "News page",
            },
            bases=("wagtailcore.page",),
        ),
        migrations.CreateModel(
            name="TrainingPage",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                ("subtitle", models.CharField(blank=True, max_length=255)),
                ("summary", models.TextField(blank=True)),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [("heading", 0), ("paragraph", 1), ("image", 2), ("quote", 3)],
                        blank=True,
                        block_lookup={
                            0: ("wagtail.blocks.CharBlock", (), {"form_classname": "title", "icon": "title"}),
                            1: (
                                "wagtail.blocks.RichTextBlock",
                                (),
                                {
                                    "features": [
                                        "h2",
                                        "h3",
                                        "bold",
                                        "italic",
                                        "ol",
                                        "ul",
                                        "link",
                                        "document-link",
                                        "image",
                                    ],
                                    "icon": "pilcrow",
                                },
                            ),
                            2: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            3: ("wagtail.blocks.BlockQuoteBlock", (), {}),
                        },
                    ),
                ),
                ("level", models.CharField(blank=True, max_length=80)),
                ("duration", models.CharField(blank=True, max_length=80)),
                ("source", models.CharField(blank=True, max_length=120)),
                ("external_link", models.URLField(blank=True)),
                ("is_featured", models.BooleanField(default=False)),
                (
                    "hero_image",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="wagtailimages.image",
                    ),
                ),
            ],
            options={
                "verbose_name": "Training page",
            },
            bases=("wagtailcore.page",),
        ),
    ]
