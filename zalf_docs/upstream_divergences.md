# Upstream divergences

Where `zalf-rdm/geonode` differs from upstream `GeoNode/geonode`, and why.

**Maintenance rule:** every change that adds to, or alters, fork-only code belongs
in this file in the same commit. If a change touches upstream code, say so
explicitly — those are the ones that hurt at merge time.

Each area below names the files involved so a merge conflict can be traced back
to an intentional decision rather than re-litigated from scratch.

---

## 1. DataCite / RDM metadata extension (`geonode.base`)

The fork extends `ResourceBase` with DataCite-aligned metadata so published
datasets can be minted and described to RDM standards.

**Models added** (`geonode/base/models.py`):

| Model | Note |
|---|---|
| `Funder` | |
| `FundingReference` | |
| `RelatedIdentifier` | |
| `RelatedIdentifierType` | **`label` is the primary key**, not an auto id |
| `RelationType` | **`label` is the primary key**, not an auto id |

**`ResourceBase` fields added:** `abstract_translated`, `date_type`, `funders`,
`method_description`, `other_description`, `related_identifier`,
`series_information`, `subtitle`, `table_of_content`, `technical_info`,
`title_translated`, `use_contraints`.

**Migration branch.** This extension runs on its own migration lineage that was
later merged back into upstream's:

```
0086_auto_20230324_1219  →  0087_auto_20230329_1513  →  0088_auto_20230330_0640
  →  0090_auto_20230330_0718  →  0091_auto_20230331_0757
  →  0094_auto_20230331_0918  →  0095_auto_20230331_0923
       ↓ merged with upstream 0088_auto_20231019_1244 at
0096_merge_0088_auto_20231019_1244_0095_auto_20230331_0923
```

Upstream occupies the same numbers with different migrations
(`0086_linkedresource`, `0087_thesauruskeyword_icon`, `0089_resourcebase_advertised`,
`0091_create_link_asset_alter_link_type`, …). **Expect collisions on every
upstream merge that adds `base` migrations** — a new merge migration is the
normal resolution, not renumbering.

**Seed data.** `geonode/base/fixtures/initial_data.json` ships the controlled
vocabularies: 18 `base.relatedidentifiertype` rows and 27 `base.relationtype`
rows. Because `label` is the PK on both models, these rows *are* their own
identity — the integer `pk` values in the fixture are vestigial and ignored on
load.

> **Trap for tests.** `GeoNodeBaseTestSupport` loads `initial_data.json`
> (`geonode/tests/base.py:52`), so `DOI`, `IsSourceOf` and the rest already exist
> before any test body runs. Creating one with `objects.create(label=...)` raises
> `IntegrityError: duplicate key value violates unique constraint
> "base_relatedidentifiertype_pkey"`. Use
> `get_or_create(label=..., defaults={"description": ...})`, and keep
> `description` out of the lookup — several fixture rows carry an empty
> description (e.g. `IsSourceOf`), so matching on it misses and collides anyway.

**API surface:** `geonode/base/api/serializers.py`, `geonode/base/api/views.py`.
Tests: `RelatedIdentifierApiTests` in `geonode/base/api/tests.py` (issue #784).

---

## 2. ORCID-only login via Keycloak (`geonode.people`)

ORCID is brokered through ZALF's Keycloak instance and consumed with
django-allauth's `openid_connect` provider. GeoNode never talks to orcid.org
directly and **does not use the ORCID Members API** — the declared scopes are
`openid`, `email`, `profile`.

- `geonode/settings.py` — the `# ORCID` block, roughly lines 2267–2387, plus
  `INSTALLED_APPS += ("geonode.zalf",)` at the end of the file.
- `geonode/people/models.py:147` — `Profile.orcid_identifier` and
  `get_orcid_url()`.
- `geonode/people/migrations/0031_merge_20210205_0824.py` — adds the field.
- `geonode/people/adapters.py` — login plus the "log out of GeoNode and ORCID"
  flow through Keycloak's `end_session_endpoint`.
- `geonode/people/profileextractors.py` — `OrcidExtractor`.
- `geonode/people/tests_orcid_display.py`.

Full writeup: [`orcid_only_login.md`](orcid_only_login.md), including the
member-integration compliance table.

> **Open question.** `OrcidExtractor.extract_organization`
> (`profileextractors.py:247-263`) parses `affiliation.organization.
> disambiguated-organization.disambiguation-source` — hyphenated keys from the
> ORCID *record API* v3.0, not OIDC claims. The `profile` scope does not supply
> an `affiliation` object, and no test covers this path. Either a Keycloak claim
> mapper fetches the record, or the branch silently returns `None` on every
> login. Unresolved as of 2026-10-05.

---

## 3. `geonode.zalf` application

Fork-only Django app; no upstream counterpart, so it merges cleanly.

- `api/datacite.py` — DataCite integration (tests: `tests/test_datacite.py`)
- `api/cms_views.py`, `api/cms_serializers.py`, `api/cms_utils.py` — CMS endpoints
- `middleware.py` — tests in `tests/test_middleware.py`
- `views.py` `resolve_landing_uuid` — `/landing/<uuid>/`, redirects to the resource's landing
  page; DOI target of the publication workflow (tests: `tests/test_landing_redirect.py`)
- `api/views.py` `count_resource_view` — `POST /api/v2/resources/<pk>/view/`, landing page
  view counter for every resource type (tests: `tests/test_view_counter.py`)
- `models.py`, `migrations/0001_cms_initial.py` … `0003_training_extra_fields.py`
- `views.py`, `urls.py`, `admin.py`, `templatetags/`

---

## 4. Data publication workflow

See [`data_publication_workflow.md`](data_publication_workflow.md).

---

## Change log

| Date | Change | Files |
|---|---|---|
| 2026-10-05 | `RelatedIdentifierApiTests.setUp` switched from `objects.create` to `get_or_create` for `RelatedIdentifierType`/`RelationType`. Both labels are PKs already present in `initial_data.json`, so `setUp` raised `IntegrityError` on every run and the class could never pass. | `geonode/base/api/tests.py` |
| 2026-10-12 | ORCID devcontainer fixed: overrode `redis` instead of the removed `rabbitmq` service (Compose rejected the project), and pointed `django`'s `env_file` at `.devcontainer/.env_orcid`. **Upstream file touched:** `.gitignore` now ignores `.devcontainer/.env_orcid`, which holds the Keycloak client secret and matched neither existing pattern. | `.devcontainer/docker-compose-orcid.yml`, `.gitignore` |
| 2026-10-12 | `_diff_sync_user_groups` (DIFF_SYNC group strategy) simplified and commented: new members join with their role in one step (one permission recalculation instead of join + promote), and role changes compare manager/not-manager, so memberships stored with an empty role by older joins are not demoted needlessly. **Upstream code touched:** only this helper in `adapters.py`; the cherry-picked FULL/SAFE/NO_SYNC code is unchanged. | `geonode/people/adapters.py` |
| 2026-10-15 | UI review fixes (#828): the header gets a skip link, Escape closes its dropdowns, the search field and its icon buttons get accessible names, and an informational cookie notice is shown (dismissal kept in localStorage). `/privacy_cookies/` rewritten as a ZALF cookie page on the institutional layout, listing the three strictly necessary cookies. The upstream text named no controller and claimed JetPack analytics. Section headings on the institutional pages changed from h3 to h2. Header, facet and cookie strings added to the de/it/es/fr `.po` files (appended at the end, `.mo` recompiled); German "Keyword" changed to "Schlagwort". **Upstream files touched:** `base.html` wraps `{% block middle %}` in `<main id="main-content">`; `privacy-cookies.html` replaced; `locale/*/django.po` extended. | `geonode/templates/base.html`, `geonode/templates/geonode-mapstore-client/snippets/header.html`, `geonode/templates/privacy-cookies.html`, `geonode/templates/{imprint,privacy,developer,ogc_and_api,data_policy,how_to_cite,publications}.html`, `geonode/locale/{de,it,es,fr}/LC_MESSAGES/django.{po,mo}` |
| 2026-10-15 | Plain devcontainer fixed like the ORCID one: the 3-space-indented `rabbitmq:` override broke YAML parsing and the service no longer exists, now overrides `redis`. | `.devcontainer/docker-compose.yml` |
| 2026-10-15 | DOI target (#823): DataCite `url` is now `{SITEURL}/landing/<uuid>/`, a fork-only route that redirects to the landing page (`#/landing/<map|tabular-collection|dataset|document>/<pk>`). GeoNode's `/catalogue/uuid/<uuid>` (previous target) redirects to the viewer, so a data collection DOI opened the map instead of its landing page. Fork-only files only. | `geonode/zalf/views.py`, `geonode/zalf/urls.py`, `geonode/zalf/api/datacite.py`, `geonode/zalf/tests/test_landing_redirect.py`, `geonode/zalf/tests/test_datacite.py` |
| 2026-10-15 | Landing page counters (#823): `popular_count` and `download_count` are returned again by the resource API as read-only fields (the 5.0.3 merge had dropped them, so the landing page always showed none). New fork-only endpoint `POST /api/v2/resources/<pk>/view/` counts landing page visits for all resource types — GeoNode only counted the dataset embed page, so maps/data collections stayed at 0. Owner and superusers are not counted, each resource once per browser session. **Upstream file touched:** `geonode/base/api/serializers.py` (two read-only fields). | `geonode/base/api/serializers.py`, `geonode/zalf/api/views.py`, `geonode/zalf/api/urls.py`, `geonode/zalf/tests/test_view_counter.py` |
| 2026-10-15 | Metadata editor (#810): "Metadata License" added to the GN5 editor right after License — `zalf.json` entry handled by `ZalfHandler`, reusing `LicenseSubHandler` and the existing licenses autocomplete (the model field existed but was never in the schema). Category made optional (`geonode:required: false` in `zalf.json`). **Upstream file touched:** `locale/de/LC_MESSAGES/django.po/.mo` — the German description "license of the metadata" was a fuzzy guess ("Lizenz des Datensatzes") and is now "Lizenz der Metadaten". The obsolete entry `#~ msgid "Search"` was removed: it duplicated the new "Search" from #828 and made `msgfmt` fail, so the `.mo` could not be compiled from the `.po`. | `geonode/metadata/schemas/zalf.json`, `geonode/metadata/handlers/zalf.py`, `geonode/metadata/tests/test_zalf_handler.py`, `geonode/locale/de/LC_MESSAGES/django.po`, `django.mo` |
| 2026-10-21 | Data Policy page replaced (#846). The page reproduced a whole invented policy (nine numbered sections) that was never an actual ZALF or BonaRes document; it is now a short overview of the two real policies, each section linking to the published original rather than restating it. Both documents were verified against DataCite. **The ZALF link uses the Zenodo concept DOI** `10.5281/zenodo.7634986` rather than the version DOI `…7634987` given in the issue, so the page follows the policy when ZALF publishes a revision instead of pinning to the 2023 version (both resolve to the same record today). The official title of that document is German ("Richtlinie 01/2023 zum Umgang mit Forschungsdaten …"), so it is shown next to the English label — otherwise an English-page reader opens a German PDF unannounced. Hero renamed to the plural "Data Policies" per the issue's proposed content, while the navigation entry stays "Data Policy". Fork-only file; template-only, no theme CSS. | `geonode/templates/data_policy.html` |
| 2026-10-20 | Publications page rewritten (#841, #820). The previous five entries were placeholders — invented authors, journals and DOIs (#821) — and are replaced by the five real publications the issue lists, grouped into Scientific Publications, Guidelines and Technical Publications & Documentation, newest first, each title linking to its DOI. Every title, author list, year and venue was checked against Crossref (3) and DataCite (2), and the titles are reproduced as the registries hold them; **the Guidelines entry's author order was corrected** to the DataCite record (Svoboda, Hoffmann, Specka, Schmidt, Atemkeng, Meier — the issue listed the same six people in a different order). The hero keeps the short title "Publications" with a subtitle scoping the page to the repository and its services, which is what #820 asked for; the long `<h2>` in `.page-header` is reworded to match but stays invisible, since the theme sets `.zalf-institutional-content .page-header { display: none }`. Fork-only file, and template-only on purpose — the entry separators reuse the existing `hr` style rather than adding theme CSS, so the page does not wait on a `geonode-mapstore-client` package rebuild. | `geonode/templates/publications.html` |
| 2026-10-21 | About page rewritten (#847). It carried GeoNode's generic product blurb ("GeoNode is a geospatial content management system …") and said nothing about this repository; it is replaced by four sections — what the repository is, its history as a timeline, who operates it, and how to reach support. **The "On this page" navigation the issue asks for is implemented as section anchors nested under the active entry in the side panel (#858) rather than as a second navigation block below the introduction**, so the page has one navigation element instead of two; `institutional_nav.html` renders that sublist only when `url_name == 'about'`, and its items mirror the `h2` ids in `about.html` — the two must be kept in step. The contact address `dataservice@zalf.de` is taken from the issue and is **unverified**; it appears nowhere else in the fork, which uses `info@zalf.de` (imprint) and `datenschutz@zalf.de` (privacy). Timeline CSS is inline, for the same reason the panel's is. Fork-only files. | `geonode/templates/about.html`, `geonode/templates/zalf/institutional_nav.html` |
| 2026-10-21 | Section navigation on the static pages (#858). The institutional pages were dead ends — each overrode `body_outer` with one full-width column, so the only way between them was the navigation bar or the footer. `zalf/institutional_base.html` now owns a two-column layout and the pages fill a new `institutional_body` block instead of `body_outer`; a page left on `body_outer` would silently render without the panel, which is why all ten were switched in one go. The panel (`zalf/institutional_nav.html`) is grouped Resources / About / Legal to match the navigation bar and footer, marks the current page from `request.resolver_match.url_name`, and gives the URL-only pages (API & Services, Cookies) a way in. **Its CSS is inline in the snippet**, as in `snippets/header.html`, rather than in the theme stylesheet: the theme ships from the `geonode-mapstore-client` package, so keeping it here means the pages render correctly without waiting for that package to be rebuilt. Fork-only files. | `geonode/templates/zalf/institutional_base.html`, `geonode/templates/zalf/institutional_nav.html` (new), `geonode/templates/{about,data_policy,how_to_cite,imprint,ogc_and_api,privacy-cookies,privacy,publications,upload}.html`, `geonode/templates/zalf/what_is_orcid.html` |
| 2026-10-20 | "Information for Developers" removed for the initial release (#844). The `^developer/$` route and `templates/developer.html` are deleted outright — the content was not reviewed for this repository and the issue asks for it to stay non-public until it is. Every link went with it: the "Developer Access" section, its sidebar entry and the `{% url 'developer' %}` lookup in `help.html`, and the `/developer/` item in the client's `snippets/footer.html` (`zalf-rdm/geonode-mapstore-client#177`). Editing that `help.html` `blocktrans` costs no translations: its msgid is `#, fuzzy` in de/it/es/fr and therefore absent from every `.mo`, so the help body already rendered in English. The `#: .../developer.html` source-reference comments remain in the `.po` files and are pruned by the next `makemessages`. **Upstream files touched:** `geonode/urls.py` (one route removed), `geonode/templates/help.html` (Developer section removed), `geonode/templates/developer.html` (deleted). | `geonode/urls.py`, `geonode/templates/help.html`, `geonode/templates/developer.html` (deleted), `geonode/templates/geonode-mapstore-client/snippets/header.html` |
| 2026-10-20 | Navigation bar rework (#832 and sub-issues #835, #840, #842, #843, #851). **Branding:** the BonaRes logo is replaced by the white ZALF mark plus a "BonaRes Repository" wordmark — one asset (`logo_zalf_white_mark.png`, added in the client repo) and one label, so the dedicated repository logo can replace it in two edits. **Menus:** "Tools & Services" → "Tools" (Trainings dropped), "LTE Maps" → "LTE Map", "Long Term Field Experiment" → "Long Term Experiments (LTE)" (the `?q=` term is unchanged — that is what the catalogue matches), "Upload" → "Submit Data"; new "Resources" dropdown (Publications, Data Policy, How to Cite Data); "About" reduced to About + FAQ, so `/developer/` and `/ogc_and_api/` are now reachable by URL only. **Login:** "Register / Login via ORCID" + "What is ORCID?" collapsed into one "Login" button, still pointing straight at the openid_connect provider — with Keycloak enabled (`KEYCLOAK_SSO_ENABLED` forces `SOCIALACCOUNT_ONLY`/`SOCIALACCOUNT_LOGIN_ON_GET`) login must not detour via `/account/login/`. The ORCID icon is kept for the same reason the label was shortened. "What is ORCID?" moves out of the bar into the **About** dropdown (so About holds About, FAQ and What is ORCID?, one more than #842 lists) and points at a new fork-only page `/what_is_orcid/` (`templates/zalf/what_is_orcid.html`) carrying the benefits text and a login button. It must not point at `/account/login/`: `repository_sso.middleware` redirects `account_login` straight to the provider when Keycloak SSO is on, so the ORCID panel in `templates/account/login.html` never renders and is effectively dead. #843's "remove What is ORCID?" item is deliberately **not** applied. **Upstream files touched:** `locale/{de,it,es,fr}/django.po/.mo` — seven navigation strings added, and 56 duplicate `msgid` definitions removed (45 it, 2 es, 3 fr, plus 6 wrap-only twins) that had made `msgfmt` refuse to rebuild those three catalogues since before this change; no msgid and no translation was lost. The matching stylesheet, client-side navigation and logo asset live in `zalf-rdm/geonode-mapstore-client#173`. #836 (hide Topics without datasets) is **not** part of this change — it needs a backend query. | `geonode/templates/geonode-mapstore-client/snippets/{header,brand_navbar_default_right_menu_items}.html`, `geonode/templates/zalf/what_is_orcid.html`, `geonode/urls.py`, `geonode/locale/{de,it,es,fr}/LC_MESSAGES/django.{po,mo}` |
| 2026-10-20 | Footer rework (#839). Description replaced with "A repository for publishing, discovering, and reusing agricultural research data." The two link columns are regrouped from "Quick Links"/"Resources" into **Repository** (About the Repository, Upload, API & Services, Data Policy, How to Cite) plus a **Legal** group (Imprint, Privacy Policy) that sits underneath the repository description in the first column, as in the issue's mockup, leaving three columns of `col-md-4`; "Research Data Management" and "Publications" dropped. "Certified By" → "Certification" with the CoreTrustSeal logo now linked to the certification record (`https://doi.org/10.34894/YPU0UO`, valid to 2028-06-12, taken from the repository's re3data entry), and "Powered by" → "Operated by ZALF" with the logo linked to zalf.de. "Upload" keeps pointing at `/upload/`, which the ingress routes to the separate Upload Tool deployment. **Upstream files touched:** `locale/{de,it,es,fr}/django.po` — ten footer strings added and all four `.mo` rebuilt — possible once #832 merged and removed the duplicate `msgid`s that had made `msgfmt` refuse it/es/fr. The client-side copy of this footer is `zalf-rdm/geonode-mapstore-client#175`. | `geonode/templates/zalf/institutional_footer.html`, `geonode/locale/{de,it,es,fr}/LC_MESSAGES/django.{po,mo}` |
---

## Not yet catalogued

This file was started on 2026-10-05 and is **incomplete**. The four areas above
are the ones confirmed by inspection; the following are known or suspected
divergences that still need writing up:

- `geonode/upload/` — the fork carries `validation/datasets.py` and
  `UploadPermissionsFilter`; unclear how much is fork-only.
- `contrib_datapackage` — the datapackage contrib module and its GeoNode-side
  hooks (recent work under issue #38).
- `geonode-mapstore-client` — any fork patches in the client repo.
- `geonode/settings.py` beyond the ORCID block.
- Templates and static assets under `geonode/templates/`, `geonode/static/`.
- Anything in the `gn_worktrees/` branches not yet merged to `main`.

When adding an area, record *why* the divergence exists, not just what changed —
that is what a future merge needs in order to decide whether to keep it.
