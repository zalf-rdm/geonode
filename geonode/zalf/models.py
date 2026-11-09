from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import translation
from django.utils.text import slugify

from geonode.assets.models import Asset, cleanup_asset_data

# Locales the CMS content is authored in. The base field carries the English /
# default value; these mirror the five locales the client ships translations
# for. A blank translation falls back to the base field.
TRANSLATED_LANGUAGES = ("de", "fr", "es", "it")


def translated_field_names(*fields):
    """`("title",)` -> `["title_de", "title_fr", "title_es", "title_it"]`, for serializers and admin."""
    return [f"{field}_{code}" for field in fields for code in TRANSLATED_LANGUAGES]


class LocalizedFieldsMixin:
    """`localized(field)` for models carrying `<field>_<lang>` variants of `TRANSLATED_FIELDS`."""

    TRANSLATED_FIELDS = ()

    def localized(self, field, lang=None):
        """The value of `field` for `lang` (default: the active language), falling back to the base field."""
        code = (lang or translation.get_language() or "en").split("-")[0].lower()
        translated = getattr(self, f"{field}_{code}", "") if code in TRANSLATED_LANGUAGES else ""
        return (translated or "").strip() or getattr(self, field)


class HighlightedCase(LocalizedFieldsMixin, models.Model):
    TRANSLATED_FIELDS = ("tab_label", "eyebrow", "title", "button_text", "body_markdown")

    tab_label = models.CharField(max_length=40)
    tab_label_de = models.CharField(max_length=40, blank=True, default="")
    tab_label_fr = models.CharField(max_length=40, blank=True, default="")
    tab_label_es = models.CharField(max_length=40, blank=True, default="")
    tab_label_it = models.CharField(max_length=40, blank=True, default="")
    eyebrow = models.CharField(max_length=60, default="HIGHLIGHTED CASE")
    eyebrow_de = models.CharField(max_length=60, blank=True, default="")
    eyebrow_fr = models.CharField(max_length=60, blank=True, default="")
    eyebrow_es = models.CharField(max_length=60, blank=True, default="")
    eyebrow_it = models.CharField(max_length=60, blank=True, default="")
    title = models.CharField(max_length=160)
    title_de = models.CharField(max_length=160, blank=True, default="")
    title_fr = models.CharField(max_length=160, blank=True, default="")
    title_es = models.CharField(max_length=160, blank=True, default="")
    title_it = models.CharField(max_length=160, blank=True, default="")
    button_text = models.CharField(max_length=40, default="View case")
    button_text_de = models.CharField(max_length=40, blank=True, default="")
    button_text_fr = models.CharField(max_length=40, blank=True, default="")
    button_text_es = models.CharField(max_length=40, blank=True, default="")
    button_text_it = models.CharField(max_length=40, blank=True, default="")
    href = models.CharField(max_length=500)
    image = models.ImageField(upload_to="cms/cases/", blank=True, null=True)
    body_markdown = models.TextField(blank=True)
    body_markdown_de = models.TextField(blank=True, default="")
    body_markdown_fr = models.TextField(blank=True, default="")
    body_markdown_es = models.TextField(blank=True, default="")
    body_markdown_it = models.TextField(blank=True, default="")
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


class SpotlightBanner(LocalizedFieldsMixin, models.Model):
    TRANSLATED_FIELDS = ("kicker", "title", "description", "button_text")

    kicker = models.CharField(max_length=80)
    kicker_de = models.CharField(max_length=80, blank=True, default="")
    kicker_fr = models.CharField(max_length=80, blank=True, default="")
    kicker_es = models.CharField(max_length=80, blank=True, default="")
    kicker_it = models.CharField(max_length=80, blank=True, default="")
    title = models.CharField(max_length=120)
    title_de = models.CharField(max_length=120, blank=True, default="")
    title_fr = models.CharField(max_length=120, blank=True, default="")
    title_es = models.CharField(max_length=120, blank=True, default="")
    title_it = models.CharField(max_length=120, blank=True, default="")
    description = models.CharField(max_length=240, blank=True)
    description_de = models.CharField(max_length=240, blank=True, default="")
    description_fr = models.CharField(max_length=240, blank=True, default="")
    description_es = models.CharField(max_length=240, blank=True, default="")
    description_it = models.CharField(max_length=240, blank=True, default="")
    button_text = models.CharField(max_length=40)
    button_text_de = models.CharField(max_length=40, blank=True, default="")
    button_text_fr = models.CharField(max_length=40, blank=True, default="")
    button_text_es = models.CharField(max_length=40, blank=True, default="")
    button_text_it = models.CharField(max_length=40, blank=True, default="")
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


class TrainingResource(LocalizedFieldsMixin, models.Model):
    # `organizer` is a proper name and stays single-language.
    TRANSLATED_FIELDS = ("title", "category", "duration", "body_markdown")

    title = models.CharField(max_length=160)
    title_de = models.CharField(max_length=160, blank=True, default="")
    title_fr = models.CharField(max_length=160, blank=True, default="")
    title_es = models.CharField(max_length=160, blank=True, default="")
    title_it = models.CharField(max_length=160, blank=True, default="")
    organizer = models.CharField(max_length=120)
    category = models.CharField(max_length=80, blank=True, default="")
    category_de = models.CharField(max_length=80, blank=True, default="")
    category_fr = models.CharField(max_length=80, blank=True, default="")
    category_es = models.CharField(max_length=80, blank=True, default="")
    category_it = models.CharField(max_length=80, blank=True, default="")
    format = models.CharField(max_length=20, choices=FORMAT_CHOICES, blank=True, default="")
    duration = models.CharField(max_length=60, blank=True, default="")
    duration_de = models.CharField(max_length=60, blank=True, default="")
    duration_fr = models.CharField(max_length=60, blank=True, default="")
    duration_es = models.CharField(max_length=60, blank=True, default="")
    duration_it = models.CharField(max_length=60, blank=True, default="")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    course_url = models.CharField(max_length=500, blank=True, default="")
    thumbnail = models.ImageField(upload_to="cms/training/", blank=True, null=True)
    body_markdown = models.TextField(blank=True)
    body_markdown_de = models.TextField(blank=True, default="")
    body_markdown_fr = models.TextField(blank=True, default="")
    body_markdown_es = models.TextField(blank=True, default="")
    body_markdown_it = models.TextField(blank=True, default="")
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


# ---------------------------------------------------------------------------
# Topics (zalf-rdm/geonode#863)
#
# "Topics" used to be hardcoded three times over — in the server navbar
# (templates/geonode-mapstore-client/snippets/header.html), in the client navbar
# (now deleted) and in the homepage grid — and the lists had already drifted
# apart. One table replaces all three, and each topic now says *how* it searches
# instead of only ever being a free-text `?q=` term.
# ---------------------------------------------------------------------------

# Locales the Topic labels are authored in; the same set as the CMS content above.
TOPIC_TRANSLATED_LANGUAGES = TRANSLATED_LANGUAGES

NAVBAR_TOPICS_CACHE_KEY = "zalf_navbar_topics_v1"
# Short on purpose: CACHES["default"] is LocMemCache unless MEMCACHED_ENABLED,
# and LocMem is per-process, so the cache.delete() below cannot reach sibling
# gunicorn workers. The TTL bounds worst-case staleness there; the delete keeps
# memcached deployments instant.
NAVBAR_TOPICS_CACHE_TTL = 60


def topic_catalogue_href(search_term="", filters=None):
    """
    The catalogue URL for a topic — the single source of truth for that string.

    Rows AND together (distinct query keys); the values within a row OR together,
    because dynamic-rest collects repeated `...in` params into a list.

    `quote_via=quote` matters: urlencode defaults to quote_plus, which would turn
    a space into "+" and give `?q=Soil+Profiles` where every previously hardcoded
    link said `?q=Soil%20Profiles`. The client parses the hash with Node's legacy
    url.parse, which happens to decode "+" as a space, so both forms work — but
    %20 keeps the generated URLs byte-identical to the ones they replace and
    matches encodeURIComponent, which is what the sibling client-side helper
    ZalfLandingPageUtils.getCategoryFilterHref produces for the same filters.
    """
    pairs = [(row["key"], value) for row in (filters or []) for value in (row.get("values") or [])]
    if search_term:
        pairs.append(("q", search_term))
    if not pairs:
        return "/catalogue/#/"
    return "/catalogue/#/?" + urlencode(pairs, quote_via=quote)


class Topic(LocalizedFieldsMixin, models.Model):
    """A curated catalogue entry point, shown in the navbar and on the homepage."""

    TRANSLATED_FIELDS = ("name",)

    name = models.CharField(max_length=120, help_text="English / default label.")
    name_de = models.CharField(max_length=120, blank=True, default="")
    name_fr = models.CharField(max_length=120, blank=True, default="")
    name_es = models.CharField(max_length=120, blank=True, default="")
    name_it = models.CharField(max_length=120, blank=True, default="")

    slug = models.SlugField(unique=True, blank=True)

    # Free-text catalogue search — the historical `?q=` behaviour. Optional.
    search_term = models.CharField(max_length=200, blank=True, default="")

    # Facet-driven filters: a list of rows shaped
    #   {"field": <facet name>, "key": "filter{...}", "values": [...], "labels": [...]}
    # Validated against the facets registry in api/topic_filters.py.
    filters = models.JSONField(default=list, blank=True)

    # Homepage card illustration. The navbar dropdown stays text-only.
    image = models.ImageField(upload_to="cms/topics/", blank=True, null=True)

    # Name of an outline icon drawn on the homepage card, in the card's own
    # colour. Deliberately NOT a `choices` enum: the icons are SVG paths that
    # live in the client (themes/zalf/utils/TopicIcons.js), which also renders
    # the picker, so the client is the single source of the vocabulary. A
    # `choices` list here would be a second list to keep in step across two
    # repos -- exactly the drift this model was added to remove. An unknown name
    # simply renders no icon.
    icon = models.CharField(
        max_length=40,
        blank=True,
        default="",
        validators=[RegexValidator(r"^[a-z0-9-]*$", "Use lowercase letters, digits and hyphens.")],
        help_text="Outline icon for the homepage card. Pick one in the CMS Topics editor, which lists the icons the site can draw.",
    )

    # The navbar and the homepage have always shown different subsets. Modelling
    # that keeps the difference an editable choice instead of an invisible
    # divergence between two source files.
    show_in_navbar = models.BooleanField(default=True)
    show_on_homepage = models.BooleanField(default=True)

    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # "id" breaks ties: the sibling models order on `order` alone, and a tie
        # there renders in nondeterministic DB order — the exact kind of drift
        # this model exists to remove.
        ordering = ("order", "id")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            while Topic.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def clean(self):
        from geonode.zalf.api.topic_filters import validate_filter_spec

        # Raises django.core.exceptions.ValidationError, so the admin shows it
        # as a form error and the DRF serializer can translate it.
        self.filters = validate_filter_spec(self.filters)

    def localized_name(self, lang=None):
        """The label for `lang`, falling back to `name` when the translation is blank."""
        return self.localized("name", lang)

    @property
    def catalogue_href(self):
        return topic_catalogue_href(self.search_term, self.filters)


def navbar_topic_rows():
    """
    Cached raw rows for the navbar.

    Language-independent on purpose: one cache entry for every locale means a
    single cache.delete() invalidates them all. The label is resolved per
    request by the template tag.
    """
    rows = cache.get(NAVBAR_TOPICS_CACHE_KEY)
    if rows is None:
        rows = [
            {
                "name": topic.name,
                **{f"name_{code}": getattr(topic, f"name_{code}") for code in TOPIC_TRANSLATED_LANGUAGES},
                "href": topic.catalogue_href,
            }
            for topic in Topic.objects.filter(is_active=True, show_in_navbar=True)
        ]
        cache.set(NAVBAR_TOPICS_CACHE_KEY, rows, NAVBAR_TOPICS_CACHE_TTL)
    return rows


@receiver(post_save, sender=Topic)
@receiver(post_delete, sender=Topic)
def invalidate_navbar_topics_cache(sender, instance, **kwargs):
    # A signal rather than a serializer hook, so the admin, the API, loaddata
    # and `manage.py shell` all invalidate. Mirrors geonode/themes/models.py.
    cache.delete(NAVBAR_TOPICS_CACHE_KEY)


# ---------------------------------------------------------------------------
# Homepage section order (zalf-rdm/geonode#863)
# ---------------------------------------------------------------------------

# The homepage sections whose content comes from this CMS, in their historical
# order. The hero is not listed: it is static chrome and always renders first.
#
# `banners` (the Spotlight carousel) was dropped from the homepage by commit
# 09f2524d0 while its model, API, CMS tab and CSS all stayed. It is restored here
# as an ordinary section so every CMS content type has one.
HOMEPAGE_SECTION_CHOICES = [
    ("cases", "Highlighted Datasets"),
    ("topics", "Browse by Topic"),
    ("banners", "Spotlight Banners"),
    ("trainings", "Training Resources"),
]

HOMEPAGE_SECTIONS_CACHE_KEY = "zalf_homepage_sections_v1"


class HomepageSection(models.Model):
    """
    Order and visibility of the CMS-driven homepage sections.

    A fixed set of rows, one per known section, seeded by migration: the CMS
    reorders and hides them but never creates or deletes them, so the API
    exposes no create/delete either.
    """

    key = models.CharField(max_length=32, choices=HOMEPAGE_SECTION_CHOICES, unique=True)
    order = models.PositiveSmallIntegerField(default=0)
    # Hides the section even when it has content, which `is_active` on the
    # content models cannot express (they hide individual records).
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.get_key_display()

    @property
    def label(self):
        return self.get_key_display()


def homepage_section_order():
    """The keys of the active homepage sections, in display order."""
    rows = cache.get(HOMEPAGE_SECTIONS_CACHE_KEY)
    if rows is None:
        rows = list(HomepageSection.objects.filter(is_active=True).values_list("key", flat=True))
        cache.set(HOMEPAGE_SECTIONS_CACHE_KEY, rows, NAVBAR_TOPICS_CACHE_TTL)
    return rows


@receiver(post_save, sender=HomepageSection)
@receiver(post_delete, sender=HomepageSection)
def invalidate_homepage_sections_cache(sender, instance, **kwargs):
    cache.delete(HOMEPAGE_SECTIONS_CACHE_KEY)


# ---------------------------------------------------------------------------
# Download packages (zalf-rdm/geonode#659)
#
# One ZIP per published data collection (map), holding every resource the
# publication made publicly downloadable. The ZIP is an Asset linked to the map,
# so GeoNode's asset endpoint, permission check and delete cleanup apply to it;
# `S3Asset` keeps its bytes in S3-compatible object storage (Hetzner first) so
# downloads do not cross the institute's uplink.
# ---------------------------------------------------------------------------


class S3Asset(Asset):
    """An Asset whose single file is an object in S3-compatible storage."""

    bucket = models.CharField(max_length=255)
    key = models.CharField(max_length=1024)
    size = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name_plural = "S3 assets"

    def __str__(self):
        return f"{self.__class__.__name__}: {self.type}|{self.bucket}/{self.key}"


# Same cleanup as LocalAsset: deleting the asset removes the stored object.
post_delete.connect(cleanup_asset_data, sender=S3Asset)


class DownloadPackage(models.Model):
    """Build state of a map's download package; the file itself is `asset`."""

    STATE_PENDING = "pending"
    STATE_BUILDING = "building"
    STATE_READY = "ready"
    STATE_FAILED = "failed"
    STATE_CHOICES = [
        (STATE_PENDING, "Pending"),
        (STATE_BUILDING, "Building"),
        (STATE_READY, "Ready"),
        (STATE_FAILED, "Failed"),
    ]

    map = models.OneToOneField("maps.Map", on_delete=models.CASCADE, related_name="zalf_download_package")
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default=STATE_PENDING)
    # SET_NULL: the asset goes with the map's links when the map is deleted, and a
    # rebuild deletes the previous one; neither may take this row with it.
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    task_id = models.CharField(max_length=255, blank=True, default="")
    error = models.TextField(blank=True, default="")
    size = models.BigIntegerField(null=True, blank=True)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    built_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Download package for map {self.map_id} ({self.state})"

    @property
    def is_ready(self):
        return self.state == self.STATE_READY and self.asset_id is not None
