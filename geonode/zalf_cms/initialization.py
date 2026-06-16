from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files import File
from django.db import transaction

from wagtail.images import get_image_model
from wagtail.models import GroupPagePermission, Page

from geonode.zalf_cms.models import (
    Banner,
    HighlightCase,
    NewsIndexPage,
    NewsPage,
    TrainingIndexPage,
    TrainingPage,
    ZalfCmsSectionsPage,
)


DEFAULT_BANNERS = [
    {
        "eyebrow": "The global hub for agricultural data",
        "title": "BonaRes Repository",
        "subtitle": "Search, discover, and reuse agricultural data from long-term experiments, monitoring programs, and curated research collections.",
        "link": "/about",
        "button_label": "About BonaRes",
        "image": "bonares-hero.jpg",
        "order": 0,
    }
]

DEFAULT_HIGHLIGHT_CASES = [
    {
        "title": "Track soil health patterns across curated agricultural datasets.",
        "subtitle": "Soil Health",
        "description": "Track soil health patterns across curated agricultural datasets.",
        "link": "/catalogue/#/?q=Soil%20Profiles",
        "button_text": "View case",
        "order": 0,
    },
    {
        "title": "Connect climate indicators with discoverable long-term observation records.",
        "subtitle": "Climate Signals",
        "description": "Connect climate indicators with discoverable long-term observation records.",
        "link": "/catalogue/#/?q=Climate",
        "button_text": "View case",
        "order": 1,
    },
    {
        "title": "Surface water, field monitoring, and hydrology collections in one focused entry point.",
        "subtitle": "Hydrology",
        "description": "Surface water, field monitoring, and hydrology collections in one focused entry point.",
        "link": "/catalogue/#/?q=Hydrology",
        "button_text": "View case",
        "order": 2,
    },
    {
        "title": "Highlight land use transitions and landscape data with an editorial presentation.",
        "subtitle": "Land Use",
        "description": "Highlight land use transitions and landscape data with an editorial presentation.",
        "link": "/catalogue/#/?q=Landscape",
        "button_text": "View case",
        "order": 3,
    },
    {
        "title": "Feature biodiversity-related records through a guided, visual discovery experience.",
        "subtitle": "Biodiversity",
        "description": "Feature biodiversity-related records through a guided, visual discovery experience.",
        "link": "/catalogue/#/?q=Animals",
        "button_text": "View case",
        "order": 4,
    },
]

HIGHLIGHT_CASE_IMAGE_FILES = {
    "Track soil health patterns across curated agricultural datasets.": "soil-health.avif",
    "Connect climate indicators with discoverable long-term observation records.": "climate-signals.avif",
    "Surface water, field monitoring, and hydrology collections in one focused entry point.": "hydrology.avif",
    "Highlight land use transitions and landscape data with an editorial presentation.": "land-use.avif",
    "Feature biodiversity-related records through a guided, visual discovery experience.": "biodiversity.avif",
}

DEFAULT_TRAININGS = [
    {
        "title": "How to make your Data FAIR 101",
        "slug": "how-to-make-your-data-fair-101",
        "summary": "Introductory training on making agricultural and environmental datasets FAIR.",
        "source": "ZALF RDM",
        "is_featured": True,
    },
    {
        "title": "Data Quality Dimensions",
        "slug": "data-quality-dimensions",
        "summary": "Overview of data quality dimensions relevant to publishing and reusing research data.",
        "source": "Leibniz Hannover University",
        "is_featured": True,
    },
    {
        "title": "Creating a KA6 Soil Dataset",
        "slug": "creating-a-ka6-soil-dataset",
        "summary": "Practical guidance for assembling and describing a KA6 soil dataset for publication.",
        "source": "Leibniz Hannover University",
        "is_featured": True,
    },
    {
        "title": "Connecting WFS/WMS Services in QGIS",
        "slug": "connecting-wfs-wms-services-in-qgis",
        "summary": "Hands-on training for connecting OGC services from the repository into QGIS.",
        "source": "Geosolutions",
        "is_featured": True,
    },
]

DEFAULT_NEWS = [
    {
        "title": "Highlight a featured soil data story",
        "slug": "highlight-a-featured-soil-data-story",
        "subtitle": "Editorial card",
        "summary": "Use this format for a large visual card with one message, one destination, and strong editorial emphasis.",
        "external_link": "/catalogue/#/?q=soil",
        "is_featured": True,
        "image": "soil-health.avif",
    },
    {
        "title": "Promote a thematic climate collection",
        "slug": "promote-a-thematic-climate-collection",
        "subtitle": "Campaign card",
        "summary": "This can point to a custom page, a filtered catalogue view, or a fully editorial landing page.",
        "external_link": "/catalogue/#/?q=climate",
        "is_featured": True,
        "image": "climate-signals.avif",
    },
    {
        "title": "Surface updates, calls, and repository news",
        "slug": "surface-updates-calls-and-repository-news",
        "subtitle": "Announcement card",
        "summary": "The design supports any number of cards, with automatic sliding and manual navigation.",
        "external_link": "/catalogue/#/?q=water",
        "is_featured": True,
        "image": "hydrology.avif",
    },
]

ROOT_PAGE_PERMISSION_CODENAMES = [
    "add_page",
    "change_page",
    "publish_page",
    "lock_page",
    "unlock_page",
]

SEED_BASE_DIR = Path(__file__).resolve().parent / "seed_assets"
HIGHLIGHT_CASE_ASSET_DIR = SEED_BASE_DIR / "highlight_cases"
BANNER_ASSET_DIR = SEED_BASE_DIR / "banners"

SECTION_ROOT = {
    "title": "ZALF CMS Sections",
    "slug": "zalf-cms-sections",
    "intro": "Administrative containers that separate editorial content by section.",
}

TRAINING_SECTION = {
    "title": "Training Resources",
    "slug": "training-resources",
    "intro": "All training pages used by the homepage and related editorial flows.",
}

NEWS_SECTION = {
    "title": "Editorial and News",
    "slug": "editorial-and-news",
    "intro": "Homepage spotlight cards, announcements, and editorial news items.",
}


def _assign_group_permissions(group_name):
    group, _ = Group.objects.get_or_create(name=group_name)
    group.permissions.add(
        *Permission.objects.filter(
            content_type__app_label__in=["zalf_cms", "wagtailadmin"],
            codename__in=[
                "access_admin",
                "add_banner",
                "change_banner",
                "delete_banner",
                "view_banner",
                "add_highlightcase",
                "change_highlightcase",
                "delete_highlightcase",
                "view_highlightcase",
                "add_trainingpage",
                "change_trainingpage",
                "delete_trainingpage",
                "view_trainingpage",
                "add_newspage",
                "change_newspage",
                "delete_newspage",
                "view_newspage",
            ],
        )
    )

    root = Page.get_first_root_node()
    for permission in Permission.objects.filter(
        content_type__app_label="wagtailcore",
        codename__in=ROOT_PAGE_PERMISSION_CODENAMES,
    ):
        GroupPagePermission.objects.get_or_create(
            group=group,
            page=root,
            permission=permission,
        )
    return group


def _assign_staff_users_to_editors():
    editors = Group.objects.get(name="Editors")
    user_model = get_user_model()
    for user in user_model.objects.filter(is_staff=True, is_superuser=False):
        user.groups.add(editors)


def sync_staff_user_group(sender, instance, **kwargs):
    editors, _ = Group.objects.get_or_create(name="Editors")
    if instance.is_superuser:
        return
    if instance.is_staff:
        instance.groups.add(editors)
    else:
        instance.groups.remove(editors)


def _seed_banners():
    for payload in DEFAULT_BANNERS:
        defaults = {**payload, "is_active": True}
        image = _get_or_create_banner_image(payload.get("image"))
        if image:
            defaults["image"] = image
        Banner.objects.update_or_create(
            title=payload["title"],
            defaults=defaults,
        )


def _ensure_section_page(parent, model, payload):
    page = model.objects.filter(slug=payload["slug"]).first()
    field_values = {
        "title": payload["title"],
        "slug": payload["slug"],
        "intro": payload["intro"],
    }

    if page:
        has_changes = any(getattr(page, field_name) != value for field_name, value in field_values.items())
        needs_move = page.get_parent().specific.id != parent.specific.id
        if has_changes:
            for field_name, value in field_values.items():
                setattr(page, field_name, value)
            page.save()
            page.save_revision().publish()
        if needs_move:
            page.move(parent, pos="last-child")
        return page.specific

    page = model(**field_values)
    parent.add_child(instance=page)
    page.save_revision().publish()
    return page.specific


def _ensure_section_structure():
    wagtail_root = Page.get_first_root_node().specific
    section_root = _ensure_section_page(wagtail_root, ZalfCmsSectionsPage, SECTION_ROOT)
    training_section = _ensure_section_page(section_root, TrainingIndexPage, TRAINING_SECTION)
    news_section = _ensure_section_page(section_root, NewsIndexPage, NEWS_SECTION)
    return training_section, news_section


def _relocate_existing_pages(target_parent, model):
    for page in model.objects.all():
        if page.get_parent().specific.id == target_parent.specific.id:
            continue
        page.move(target_parent, pos="last-child")


def _seed_highlight_cases():
    for payload in DEFAULT_HIGHLIGHT_CASES:
        defaults = {**payload, "is_active": True}
        image = _get_or_create_highlight_case_image(payload["title"])
        if image:
            defaults["image"] = image
        HighlightCase.objects.update_or_create(
            title=payload["title"],
            defaults=defaults,
        )


def _get_or_create_highlight_case_image(case_title):
    filename = HIGHLIGHT_CASE_IMAGE_FILES.get(case_title)
    if not filename:
        return None

    asset_path = HIGHLIGHT_CASE_ASSET_DIR / filename
    if not asset_path.exists():
        return None

    image_title = f"ZALF Highlight Case - {filename}"
    image_model = get_image_model()
    image = image_model.objects.filter(title=image_title).first()
    if image:
        return image

    with asset_path.open("rb") as handle:
        image = image_model(title=image_title)
        image.file.save(filename, File(handle), save=True)
    return image


def _get_or_create_banner_image(filename):
    if not filename:
        return None
    return _get_or_create_seed_image(
        filename,
        "ZALF Banner",
        BANNER_ASSET_DIR,
    )


def _get_or_create_seed_image(filename, image_title_prefix, asset_dir):
    asset_path = asset_dir / filename
    if not asset_path.exists():
        return None

    image_title = f"{image_title_prefix} - {filename}"
    image_model = get_image_model()
    image = image_model.objects.filter(title=image_title).first()
    if image:
        return image

    with asset_path.open("rb") as handle:
        image = image_model(title=image_title)
        image.file.save(filename, File(handle), save=True)
    return image


def _get_or_create_news_image(filename):
    return _get_or_create_seed_image(
        filename,
        "ZALF Spotlight",
        HIGHLIGHT_CASE_ASSET_DIR,
    )


def _upsert_training_page(root, payload):
    page = TrainingPage.objects.filter(slug=payload["slug"]).first()
    field_values = {
        "title": payload["title"],
        "slug": payload["slug"],
        "summary": payload["summary"],
        "source": payload["source"],
        "is_featured": payload["is_featured"],
    }

    if page:
        has_changes = any(getattr(page, field_name) != value for field_name, value in field_values.items())
        if not has_changes and page.live:
            return
        for field_name, value in field_values.items():
            setattr(page, field_name, value)
        page.save()
    else:
        page = TrainingPage(**field_values)
        root.add_child(instance=page)

    revision = page.save_revision()
    revision.publish()


def _seed_training_pages():
    root, _ = _ensure_section_structure()
    _relocate_existing_pages(root, TrainingPage)
    for payload in DEFAULT_TRAININGS:
        _upsert_training_page(root, payload)


def _upsert_news_page(root, payload, hero_image=None):
    page = NewsPage.objects.filter(slug=payload["slug"]).first()
    field_values = {
        "title": payload["title"],
        "slug": payload["slug"],
        "subtitle": payload["subtitle"],
        "summary": payload["summary"],
        "external_link": payload["external_link"],
        "is_featured": payload["is_featured"],
    }
    if hero_image:
        field_values["hero_image"] = hero_image

    if page:
        has_changes = any(getattr(page, field_name) != value for field_name, value in field_values.items())
        if not has_changes and page.live:
            return
        for field_name, value in field_values.items():
            setattr(page, field_name, value)
        page.save()
    else:
        page = NewsPage(**field_values)
        root.add_child(instance=page)

    revision = page.save_revision()
    revision.publish()


def _seed_news_pages():
    _, root = _ensure_section_structure()
    _relocate_existing_pages(root, NewsPage)
    for payload in DEFAULT_NEWS:
        hero_image = _get_or_create_news_image(payload["image"])
        _upsert_news_page(root, payload, hero_image=hero_image)


@transaction.atomic
def bootstrap_zalf_cms(**kwargs):
    _assign_group_permissions("Editors")
    _assign_group_permissions("Moderators")
    _assign_staff_users_to_editors()
    _seed_banners()
    _seed_highlight_cases()
    _seed_training_pages()
    _seed_news_pages()
