from django.templatetags.static import static
from django.utils.html import format_html

from wagtail import hooks
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from geonode.zalf_cms.models import Banner, HighlightCase


@hooks.register("insert_global_admin_css")
def zalf_cms_admin_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("zalf_cms/css/wagtail_admin_zalf.css"),
    )


@hooks.register("insert_global_admin_js")
def zalf_cms_admin_js():
    return format_html(
        '<script src="{}"></script>',
        static("zalf_cms/js/wagtail_admin_zalf.js"),
    )


class BannerViewSet(SnippetViewSet):
    model = Banner
    icon = "image"
    menu_label = "Banners"
    menu_name = "zalf-cms-banners"
    list_display = ["title", "order", "is_active"]
    search_fields = ["title", "subtitle", "link"]
    ordering = ["order", "title"]


class HighlightCaseViewSet(SnippetViewSet):
    model = HighlightCase
    icon = "folder-open-inverse"
    menu_label = "Highlight Cases"
    menu_name = "zalf-cms-highlight-cases"
    list_display = ["title", "subtitle", "order", "is_active"]
    search_fields = ["title", "subtitle", "description", "link"]
    ordering = ["order", "title"]


class HomepageContentViewSetGroup(SnippetViewSetGroup):
    items = (BannerViewSet, HighlightCaseViewSet)
    menu_label = "Homepage Content"
    menu_name = "zalf-cms-homepage-content"
    menu_icon = "home"
    menu_order = 210


@hooks.register("register_admin_viewset")
def register_homepage_content_viewset():
    return HomepageContentViewSetGroup()
