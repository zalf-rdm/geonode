from django.db import models
from django.utils.text import slugify


class HighlightedCase(models.Model):
    tab_label = models.CharField(max_length=40)
    eyebrow = models.CharField(max_length=60, default="HIGHLIGHTED CASE")
    title = models.CharField(max_length=160)
    button_text = models.CharField(max_length=40, default="View case")
    href = models.CharField(max_length=500)
    image = models.ImageField(upload_to="cms/cases/", blank=True, null=True)
    body_markdown = models.TextField(blank=True)
    slug = models.SlugField(unique=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.tab_label or self.title)
            slug = base
            n = 1
            while HighlightedCase.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.tab_label


class SpotlightBanner(models.Model):
    kicker = models.CharField(max_length=80)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    button_text = models.CharField(max_length=40)
    href = models.CharField(max_length=500)
    image = models.ImageField(upload_to="cms/banners/", blank=True, null=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title


FORMAT_CHOICES = [
    ("on-demand", "On-demand / Self-paced"),
    ("video", "Recorded video"),
    ("live", "Live webinar"),
    ("workshop", "In-person workshop"),
]


class TrainingResource(models.Model):
    title = models.CharField(max_length=160)
    organizer = models.CharField(max_length=120)
    category = models.CharField(max_length=80, blank=True, default="")
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, blank=True, default="")
    duration = models.CharField(max_length=60, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    course_url = models.CharField(max_length=500, blank=True, default="")
    thumbnail = models.ImageField(upload_to="cms/training/", blank=True, null=True)
    body_markdown = models.TextField(blank=True)
    slug = models.SlugField(unique=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while TrainingResource.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
