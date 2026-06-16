from django.db import migrations, models
from django.utils.text import slugify


def forwards(apps, schema_editor):
    HighlightCase = apps.get_model("zalf_cms", "HighlightCase")

    for case in HighlightCase.objects.all().order_by("id"):
        if case.slug:
            continue

        base_slug = slugify(case.title) or "highlight-case"
        slug_candidate = base_slug
        counter = 2

        while HighlightCase.objects.exclude(pk=case.pk).filter(slug=slug_candidate).exists():
            slug_candidate = f"{base_slug}-{counter}"
            counter += 1

        case.slug = slug_candidate
        case.save(update_fields=["slug"])


def backwards(apps, schema_editor):
    HighlightCase = apps.get_model("zalf_cms", "HighlightCase")
    HighlightCase.objects.update(slug=None)


class Migration(migrations.Migration):
    dependencies = [
        ("zalf_cms", "0007_banner_target_page_alter_banner_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="highlightcase",
            name="slug",
            field=models.SlugField(blank=True, max_length=180, null=True, unique=True),
        ),
        migrations.RunPython(forwards, backwards),
    ]
