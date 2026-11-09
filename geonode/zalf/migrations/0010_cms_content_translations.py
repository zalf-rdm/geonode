# Per-language variants of the CMS content fields (zalf-rdm/geonode#901).
# Schema only: every variant starts blank, which falls back to the base field.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("zalf", "0009_seed_topic_icons"),
    ]

    operations = [
        migrations.AddField(
            model_name="highlightedcase",
            name="tab_label_de",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="tab_label_fr",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="tab_label_es",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="tab_label_it",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="eyebrow_de",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="eyebrow_fr",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="eyebrow_es",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="eyebrow_it",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="title_de",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="title_fr",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="title_es",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="title_it",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="button_text_de",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="button_text_fr",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="button_text_es",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="button_text_it",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="body_markdown_de",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="body_markdown_fr",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="body_markdown_es",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="highlightedcase",
            name="body_markdown_it",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="kicker_de",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="kicker_fr",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="kicker_es",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="kicker_it",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="title_de",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="title_fr",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="title_es",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="title_it",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="description_de",
            field=models.CharField(blank=True, default="", max_length=240),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="description_fr",
            field=models.CharField(blank=True, default="", max_length=240),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="description_es",
            field=models.CharField(blank=True, default="", max_length=240),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="description_it",
            field=models.CharField(blank=True, default="", max_length=240),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="button_text_de",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="button_text_fr",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="button_text_es",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="spotlightbanner",
            name="button_text_it",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="title_de",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="title_fr",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="title_es",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="title_it",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="category_de",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="category_fr",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="category_es",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="category_it",
            field=models.CharField(blank=True, default="", max_length=80),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="duration_de",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="duration_fr",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="duration_es",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="duration_it",
            field=models.CharField(blank=True, default="", max_length=60),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="body_markdown_de",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="body_markdown_fr",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="body_markdown_es",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="trainingresource",
            name="body_markdown_it",
            field=models.TextField(blank=True, default=""),
        ),
    ]
