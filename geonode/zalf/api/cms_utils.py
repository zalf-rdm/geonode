from urllib.parse import urlparse

import bleach
import markdown

ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "h2",
    "h3",
    "h4",
    "strong",
    "em",
    "u",
    "s",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "a",
    "img",
    "figure",
    "figcaption",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}

SAFE_LINK_SCHEMES = {"http", "https", ""}


def _allowed_attrs(tag, name, value):
    if tag == "a":
        if name == "href":
            scheme = urlparse(value).scheme
            return scheme in SAFE_LINK_SCHEMES
        if name in ("title", "rel", "target"):
            return True
        return False
    if tag == "img":
        return name in ("src", "alt", "width", "height")
    if tag in ("td", "th"):
        return name in ("colspan", "rowspan")
    return False


_cleaner = bleach.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=_allowed_attrs,
    strip=True,
    strip_comments=True,
)


def render_markdown(text):
    if not text:
        return ""
    raw_html = markdown.markdown(text, extensions=["extra", "nl2br"])
    return _cleaner.clean(raw_html)
