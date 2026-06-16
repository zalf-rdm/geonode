from django.db import models

from wagtail import blocks
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, PageChooserPanel
from wagtail.fields import StreamField
from wagtail.images import get_image_model_string
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page


RICH_TEXT_FEATURES = [
    "h2",
    "h3",
    "bold",
    "italic",
    "ol",
    "ul",
    "link",
    "document-link",
    "image",
]


class ContentBodyBlock(blocks.StreamBlock):
    heading = blocks.CharBlock(form_classname="title", icon="title")
    paragraph = blocks.RichTextBlock(features=RICH_TEXT_FEATURES, icon="pilcrow")
    image = ImageChooserBlock()
    quote = blocks.BlockQuoteBlock()

    class Meta:
        icon = "doc-full"


class EditorialPage(Page):
    subtitle = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    hero_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    body = StreamField(ContentBodyBlock(), blank=True, use_json_field=True)

    content_panels = Page.content_panels + [
        FieldPanel("subtitle"),
        FieldPanel("summary"),
        FieldPanel("hero_image"),
        FieldPanel("body"),
    ]

    class Meta:
        abstract = True


class ZalfCmsSectionsPage(Page):
    intro = models.TextField(blank=True)

    parent_page_types = ["wagtailcore.Page"]
    subpage_types = ["zalf_cms.TrainingIndexPage", "zalf_cms.NewsIndexPage"]
    max_count = 1

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    class Meta:
        verbose_name = "ZALF CMS sections"


class TrainingIndexPage(Page):
    intro = models.TextField(blank=True)

    parent_page_types = ["zalf_cms.ZalfCmsSectionsPage"]
    subpage_types = ["zalf_cms.TrainingPage"]
    max_count = 1

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    class Meta:
        verbose_name = "Training section"


class NewsIndexPage(Page):
    intro = models.TextField(blank=True)

    parent_page_types = ["zalf_cms.ZalfCmsSectionsPage"]
    subpage_types = ["zalf_cms.NewsPage"]
    max_count = 1

    content_panels = Page.content_panels + [
        FieldPanel("intro"),
    ]

    class Meta:
        verbose_name = "News section"


class TrainingPage(EditorialPage):
    level = models.CharField(max_length=80, blank=True)
    duration = models.CharField(max_length=80, blank=True)
    source = models.CharField(max_length=120, blank=True)
    external_link = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)

    parent_page_types = ["zalf_cms.TrainingIndexPage"]
    subpage_types = []

    content_panels = EditorialPage.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("level"),
                FieldPanel("duration"),
                FieldPanel("source"),
                FieldPanel("external_link"),
                FieldPanel("is_featured"),
            ],
            heading="Training details",
        )
    ]

    class Meta:
        verbose_name = "Training page"


class NewsPage(EditorialPage):
    published_at = models.DateField(null=True, blank=True)
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated tags for API consumers.")
    external_link = models.CharField(
        max_length=500,
        blank=True,
        help_text="Supports internal paths like /catalogue/#/... and external URLs.",
    )
    is_featured = models.BooleanField(default=False)

    parent_page_types = ["zalf_cms.NewsIndexPage"]
    subpage_types = []

    content_panels = EditorialPage.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("published_at"),
                FieldPanel("tags"),
                FieldPanel("external_link"),
                FieldPanel("is_featured"),
            ],
            heading="Publication details",
        )
    ]

    class Meta:
        verbose_name = "News page"


class Banner(models.Model):
    eyebrow = models.CharField(max_length=160, blank=True)
    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=255, blank=True)
    image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    target_page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Optional CMS page opened when the banner CTA is clicked.",
    )
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text="Fallback link. Supports internal paths like /catalogue/#/... and external URLs.",
    )
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    button_label = models.CharField(max_length=80, blank=True)

    panels = [
        FieldPanel("eyebrow"),
        FieldPanel("title"),
        FieldPanel("subtitle"),
        FieldPanel("image"),
        PageChooserPanel("target_page"),
        FieldPanel("link"),
        FieldPanel("button_label"),
        FieldPanel("order"),
        FieldPanel("is_active"),
    ]

    class Meta:
        ordering = ("order", "title")

    def __str__(self):
        return self.title


class HighlightCase(models.Model):
    title = models.CharField(max_length=160)
    subtitle = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text="Supports internal paths like /catalogue/#/... and external URLs.",
    )
    button_text = models.CharField(max_length=80, default="Explore Now")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    panels = [
        FieldPanel("title"),
        FieldPanel("subtitle"),
        FieldPanel("description"),
        FieldPanel("image"),
        FieldPanel("link"),
        FieldPanel("button_text"),
        FieldPanel("order"),
        FieldPanel("is_active"),
    ]

    class Meta:
        ordering = ("order", "title")

    def __str__(self):
        return self.title
