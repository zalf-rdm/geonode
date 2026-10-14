# UI review specification: BonaRes Repository (ZALF GeoNode)

This document defines how the public web application at
<https://repository-e.dataservice.zalf.de> is expected to look and behave. It is
written as a checklist for an AI agent (run `/ui-review [base_url]`, see
`.claude/skills/ui-review/SKILL.md`), but every requirement is phrased so that a
human can check it too.

Run it after changes to templates, the `zalf` client theme, settings that affect
the frontend, or a GeoNode / mapstore-client upgrade. The goal is not a full
audit; it is to confirm that our basic understanding of the application still
holds and to surface regressions early.

The look is split across two repositories:

- this repo: Django templates (`geonode/templates/zalf/`,
  `geonode/templates/geonode-mapstore-client/snippets/`, `base.html`,
  `account/`), server-side CSS in `geonode/static/geonode/css/`;
- `zalf-rdm/geonode-mapstore-client`: the `themes/zalf` LESS theme (design
  tokens), the React home page, navigation and footer, and `localConfig.json`
  (`zalf_home` plugin set).

A regression found here may need fixing in either one.

---

## 0. Rules of engagement

| ID | Rule |
|---|---|
| RUN-01 | The base URL is a parameter. Default: `https://repository-e.dataservice.zalf.de`. All paths below are relative to it. |
| RUN-02 | **Anonymous and read-only.** Never submit forms (except the language selector), never upload, never complete the ORCID / Keycloak login, never open `/admin/`, never send anything other than `GET`/`HEAD` requests to the API. |
| RUN-03 | Start from a fresh browser context (no cookies) so the cookie banner and silent-SSO behaviour are those of a first-time visitor. |
| RUN-04 | Viewports: desktop 1440×900, tablet 768×1024, mobile 375×812. Requirements apply to desktop unless they mention a viewport. |
| RUN-05 | Be polite to production: at most ~2 requests per second for link checks, and no more than one full run at a time. |
| RUN-06 | Every requirement gets one status: `PASS`, `FAIL`, `WARN` (SHOULD not met, or budget exceeded by less than 20%), `KNOWN` (matches an entry in §10), `N/A` (cannot apply, say why). Every non-PASS status needs evidence: URL, measured value, and a screenshot where visual. |

Requirement levels: **MUST** failures are `FAIL`; **SHOULD** failures are `WARN`.

---

## 1. Page inventory

These pages are visited for every page-level check (header, footer, contrast,
links, console, semantics). "Detail" pages are chosen at run time.

| ID | Page | Path |
|---|---|---|
| PAGE-01 | Home | `/` |
| PAGE-02 | Catalogue (all data) | `/catalogue/` |
| PAGE-03 | Catalogue, topic query | `/catalogue/#/?q=Soil%20Profiles` |
| PAGE-04 | Dataset detail | first item of `/api/v2/datasets?page_size=1` → its `detail_url` |
| PAGE-05 | Dataset map viewer | the "View" / map viewer reachable from PAGE-04 |
| PAGE-06 | Document detail | first item of `/api/v2/documents?page_size=1` → its `detail_url` |
| PAGE-07 | About | `/about/` |
| PAGE-08 | FAQ | `/faq/` |
| PAGE-09 | Developer | `/developer/` |
| PAGE-10 | OGC services and API | `/ogc_and_api/` |
| PAGE-11 | Data policy | `/data_policy/` |
| PAGE-12 | How to cite | `/how_to_cite/` |
| PAGE-13 | Publications | `/publications/` |
| PAGE-14 | Trainings | `/trainings/` |
| PAGE-15 | Imprint | `/imprint/` |
| PAGE-16 | Privacy | `/privacy/` |
| PAGE-17 | Privacy and cookies | `/privacy_cookies/` |
| PAGE-18 | Sign in | `/account/login/` |

PAGE-xx itself is `PASS` when the page returns HTTP 200 and renders visible
main content (not an error page, not a blank SPA shell after 10 s).

---

## 2. Brand and visual consistency

### 2.1 Design tokens

The source of truth is the CSS custom properties of the `zalf` theme
(`/static/mapstore/dist/themes/zalf.css`, defined in the client repo at
`themes/zalf/less/variables.less`). The values below are the ones live on
2026-10-14.

| Token | Value | Used for |
|---|---|---|
| `--zalf-brand-primary` / `--zalf-nav-bg` | `#4e9c18` | top navigation bar, primary buttons |
| `--zalf-brand-primary-hover` | `#448615` | hover on primary |
| `--zalf-brand-primary-active` | `#3a7412` | pressed/active primary |
| `--zalf-brand-primary-border` | `#3f7f14` | primary button border |
| `--zalf-brand-primary-strong` / `--zalf-green` | `#1a6b3c` | strong accents, headings on light surfaces |
| `--zalf-brand-panel-bg` / `--zalf-nav-panel-bg` | `#3b7a57` | navigation dropdown panels |
| `--zalf-brand-highlight` / `--zalf-nav-highlight` | `#c7d406` | active nav indicator |
| `--zalf-brand-surface-light` / `-mid` | `#e8f5ec` / `#c5e8d0` | light green surfaces |
| `--zalf-nav-text` | `#f4f4f4` | navigation text |
| `--zalf-bg` | `#f4f6f8` | page background |
| `--zalf-border` | `#dde3e9` | borders, dividers |
| body text / muted text | `#202124` / `#5a6672` | copy |
| `--zalf-footer-bg` | `#0b0b0b` | footer |
| `--zalf-footer-text` / `-muted` / `-link` | `#f4f4f4` / `#adb5bd` / `#4d9b70` | footer copy and links |
| `--zalf-home-idas-zalf` / `-bonares` / `-fairagro` | `#a5b600` / `#5db600` / `#78c13b` | partner tiles on home |
| `--zalf-radius` | `8px` | cards, buttons, inputs |
| `--zalf-nav-height` | `78px` | header height (desktop) |
| `--zalf-font-sans` | `"Inter", "Helvetica Neue", Helvetica, Arial, sans-serif` | body font |

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| BRAND-01 | MUST | The tokens above are defined on `:root` with these values. A changed value is reported as a change, not automatically as a failure. The reviewer states whether it looks intentional. | Read `getComputedStyle(document.documentElement).getPropertyValue('--zalf-…')` on PAGE-01. |
| BRAND-02 | MUST | Header background on every page is `--zalf-nav-bg`; footer background is `--zalf-footer-bg`. | Computed `background-color` of header and footer elements on every inventory page. |
| BRAND-03 | MUST | The BonaRes logo (`bonares-logo-white.png`) is shown at the left of the header on every page, loads (natural width > 0) and links to `/`. It has a meaningful `alt`. | DOM and screenshot. |
| BRAND-04 | MUST | The footer shows the Core Trust Seal logo ("Certified by") and the ZALF logo ("Powered by"), both loaded. | DOM and screenshot. |
| BRAND-05 | MUST | A favicon is served (`/static/geonode/img/favicon.ico`, 200). | `curl -I`. |
| BRAND-06 | SHOULD | One body font family across all pages. Headings and body use the same family stack. | Computed `font-family` of `body`, `h1`, `h2`, nav links, buttons on every page; list distinct families. |
| BRAND-07 | SHOULD | `<title>` is specific to the page (contains the page or resource name, plus the site name), not just the hostname. | `document.title` on every page. |

### 2.2 Header and navigation

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| UI-01 | MUST | The header is identical on every inventory page: same items, same order, same styling. On the map viewer (PAGE-05) a reduced header is acceptable if it still offers a way back to the catalogue. | Compare the header's visible text and link targets across pages. |
| UI-02 | MUST | Desktop navigation order: **All Data** · **Topics ▾** · **Tools & Services ▾** · **Upload** · **About ▾**, then the language selector and the ORCID sign-in. | Screenshot and DOM order. |
| UI-03 | MUST | "Topics" lists: Animals, Atmosphere, Climate, Forest, Hydrology, Landscape, Long Term Field Experiment, Plants, Soil Profiles, Water. Each links to `/catalogue/#/?q=<topic>`. | Open the dropdown, read the items. |
| UI-04 | MUST | "Tools & Services" contains Trainings (`/trainings/`), LTE Maps (`tools.bonares.de/ltfe/`), Soil Profiles (`tools.bonares.de/bp_db/`), DQ Kit (`dqkit.bonares.de`). | Open the dropdown. |
| UI-05 | MUST | "About" contains About, Developer, OGC Services and API, FAQ, Data Policy, How to Cite Us. | Open the dropdown. |
| UI-06 | MUST | At 375 px the navigation collapses into a toggle; the toggle opens a menu that exposes every item from UI-02 to UI-05, and nothing overflows horizontally. | Mobile viewport, screenshot before and after opening. |
| UI-07 | SHOULD | The current section is visibly marked (highlight `--zalf-nav-highlight` or equivalent), not by colour alone (see A11Y-04). | Screenshot on `/catalogue/` and `/about/`. |

### 2.3 Footer

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| UI-10 | MUST | The footer is identical on every inventory page (map viewer excepted). | Compare footer text and link targets across pages. |
| UI-11 | MUST | Four areas: "BonaRes Repository" description; **Quick Links** (About, Upload, OGC, ZALF Research Data Management); **Resources** (Publications, Data Policy, How to Cite, Imprint, Privacy); **Certified by** / **Powered by**. | DOM and screenshot. |
| UI-12 | MUST | A copyright line ("© BonaRes Repository …") is present. | DOM. |

### 2.4 Buttons, links, forms and cards

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| UI-20 | MUST | Primary call-to-action buttons (e.g. search, "All Data" CTA on home, "Sign in with ORCID", primary actions on detail pages) use the brand primary family (`#4e9c18`, `#448615`, `#3a7412`, `#1a6b3c`) for background or border, not MapStore/Bootstrap default blue (`#397aab`, `#0075ff`, `#337ab7`, `#2c5f85`). | Collect computed `background-color` and `border-color` of `button`, `.btn`, `[role=button]`, `a.btn` on every page; list any with a default-blue value in a ZALF-styled area. |
| UI-21 | SHOULD | Buttons of the same kind share border radius (`--zalf-radius` 8px, or fully rounded pills used consistently), font size, font weight and padding across pages. | Group buttons by class and compare computed styles; report outliers. |
| UI-22 | SHOULD | Button labels use one casing convention per kind (e.g. Title Case for primary CTAs) and one language per page. | Read labels. |
| UI-23 | MUST | Every interactive element has distinct hover and keyboard-focus states. Focus is visible (see A11Y-06). | Hover and tab through a sample of buttons and links per page. |
| UI-24 | SHOULD | Body links are recognisable as links without relying on colour alone (underline, or underline on hover plus a 3:1 contrast to surrounding text). | Screenshot plus computed `text-decoration`. |
| UI-25 | SHOULD | Dataset and document cards in the catalogue share layout: thumbnail, title, resource type, date. Missing thumbnails show a placeholder, not a broken image. | Screenshot of PAGE-02; check `img.naturalWidth > 0`. |
| UI-26 | SHOULD | No page falls back to unstyled Bootstrap/GeoNode defaults (Times-like serif, default blue navbar, raw HTML lists where cards are expected). | Visual judgement on every page. |
| UI-27 | MUST | At all three viewports there is no horizontal page scroll and no clipped or overlapping text in header, hero, cards and footer. | `document.documentElement.scrollWidth <= innerWidth`; screenshots. |

---

## 3. Accessibility (WCAG 2.2 AA / BITV 2.0)

ZALF is a publicly funded institution, so BITV 2.0 (which references WCAG 2.1 AA
through EN 301 549) applies. WCAG 2.2 AA is our target.

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| A11Y-01 | MUST | Text contrast ≥ 4.5:1; large text (≥ 24 px, or ≥ 18.66 px bold) ≥ 3:1. | Contrast script (skill snippet) over all visible text nodes on every page, at least header, hero, cards, footer, buttons. Report each failing pair once with selector, colours and ratio. |
| A11Y-02 | MUST | Non-text contrast ≥ 3:1 for UI component boundaries and focus indicators (inputs, buttons without fill, toggles, map controls). | Contrast script on borders; visual check. |
| A11Y-03 | MUST | **Colour-blind check.** Under simulated protanopia, deuteranopia, tritanopia and achromatopsia, all of these remain distinguishable: active vs. inactive nav item; selected vs. unselected catalogue filter; success vs. error states (`#3aba6f` / `#b31e13`); partner tiles on home; map legend entries on PAGE-05. | Apply the colour-blind filters (skill snippet) on PAGE-01, PAGE-02 and PAGE-05; screenshot each; judge. |
| A11Y-04 | MUST | No information is conveyed by colour alone (WCAG 1.4.1). States also carry text, an icon, an underline, a border weight or a shape. | Same screenshots as A11Y-03, plus achromatopsia. |
| A11Y-05 | MUST | All navigation dropdowns, the language selector, the mobile menu toggle, catalogue filters and the ORCID button can be reached and operated with the keyboard (Tab, Shift+Tab, Enter/Space, Escape closes dropdowns). | Keyboard walk on PAGE-01 and PAGE-02. |
| A11Y-06 | MUST | Keyboard focus is always visible (WCAG 2.4.7) and not hidden behind the sticky header (2.4.11). | Screenshot while tabbing. |
| A11Y-07 | MUST | No keyboard trap, including inside the map viewer. | Tab into and out of the map on PAGE-05. |
| A11Y-08 | SHOULD | A "skip to main content" link is the first focusable element. | First Tab on PAGE-01. |
| A11Y-09 | MUST | `<html>` has a `lang` attribute that matches the active UI language. | `document.documentElement.lang` on every page, in EN and DE. |
| A11Y-10 | MUST | Every image has an `alt` attribute (empty for decorative images); every icon-only button or link has an accessible name (`aria-label`, `title`, or hidden text). | DOM query on every page. |
| A11Y-11 | SHOULD | Exactly one `h1` per page; heading levels do not skip (h1 → h3). | DOM outline per page. |
| A11Y-12 | SHOULD | Landmarks: `header`/`banner`, `nav`, `main`, `footer`/`contentinfo` exist once each. | DOM query. |
| A11Y-13 | MUST | Form fields (catalogue search, filters) have programmatic labels. | DOM: `label[for]`, `aria-label` or `aria-labelledby`. |
| A11Y-14 | MUST | At 200% browser zoom (or 640 px CSS width) content reflows without horizontal scrolling (WCAG 1.4.10) and nothing is cut off. | Set viewport to 640×800 and check `scrollWidth`. |
| A11Y-15 | SHOULD | With `prefers-reduced-motion: reduce`, carousels and animations stop or are reduced. | Emulate reduced motion on PAGE-01. |
| A11Y-16 | MUST | An accessibility statement ("Erklärung zur Barrierefreiheit", required by BITV 2.0 §7) is reachable from every page, normally via the footer, and names a feedback contact. | Footer links; follow the link. |

---

## 4. Links and assets

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| LINK-01 | MUST | Every internal link found in the **rendered** DOM of any inventory page resolves to a 2xx, either directly or after redirects. A 3xx is only acceptable if the final response is 2xx. Hash routes (`/catalogue/#/…`) count as the path before `#`. | Link collector snippet → deduplicate → `curl -sIL -o /dev/null -w '%{http_code}'`. |
| LINK-02 | MUST | Every external link resolves to 2xx/3xx (tools.bonares.de, dqkit.bonares.de, zalf.de, coretrustseal.org, orcid.org, geonode.org, …). A 403 from bot protection counts as `WARN` with a note, not `FAIL`. | `curl -sIL` with a browser User-Agent; retry with GET if HEAD is rejected. |
| LINK-03 | MUST | Each of the ten topic links (UI-03) returns at least one result in the catalogue. | Load each topic URL and count result cards, or query `/api/v2/resources?search=<topic>` and check `total > 0`. |
| LINK-04 | MUST | No failed requests for static assets (CSS, JS, fonts, images) on any inventory page. | Browser network log or Performance API (`transferSize`, plus failed entries); `curl` each asset URL. |
| LINK-05 | MUST | No mixed content: every resource and link on an HTTPS page uses HTTPS. | Search the DOM and resource list for `http://`. |
| LINK-06 | SHOULD | External links are handled consistently: either all open in a new tab (with `rel="noopener"`) or all in the same tab, ideally with an external-link indicator. | Compare `target` and `rel` of external links. |
| LINK-07 | SHOULD | No placeholder links (`href="#"`, `href=""`, `javascript:void(0)`) on elements that are presented as links (buttons that open dropdowns are excepted). | DOM query. |

---

## 5. Anonymous functional smoke test

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| FUNC-01 | MUST | Searching the catalogue for a common term (e.g. "soil") returns results. Clearing the search returns the full list. | Type in the search field, submit, count results. |
| FUNC-02 | MUST | Resource-type filter (dataset/document/map) and sort order change the result list. | Toggle one filter and one sort option, compare the first results. |
| FUNC-03 | MUST | The dataset detail page (PAGE-04) shows title, abstract, a DOI or citation block, licence and a download or access option. | DOM and screenshot. |
| FUNC-04 | MUST | The map viewer (PAGE-05) loads the base map and the dataset layer (tile requests return 200), and the layer appears in the table of contents. | Network log and screenshot after 10 s. |
| FUNC-05 | MUST | The document detail page (PAGE-06) shows a preview or thumbnail and a download link. | DOM and screenshot. |
| FUNC-06 | MUST | "Upload" while anonymous leads to sign-in, not to an error page. | Click Upload; check the final URL. |
| FUNC-07 | MUST | "Sign in with ORCID" redirects to `identity-e.dataservice.zalf.de` (Keycloak, realm `ORCID`). **Stop there** and do not log in. | Click; record the final host and the time from click to IdP page load. |
| FUNC-08 | MUST | Loading `/` in a fresh context does not loop through the silent-SSO check (`prompt=none`): the home page renders within 5 s and the URL ends on `/`. | Load PAGE-01 and watch navigation events. |
| FUNC-09 | MUST | No uncaught JavaScript errors in the browser console on any inventory page. Warnings are listed but do not fail. | Console log per page. |
| FUNC-10 | SHOULD | The sign-in page (PAGE-18) shows the ORCID iD icon, the heading "Sign in with your ORCID iD" and the "Why do we use ORCID?" explanation. No username/password form is shown. | DOM and screenshot. |

---

## 6. Legal and compliance

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| LEGAL-01 | MUST | Imprint (Impressum, §5 DDG), Privacy (Datenschutzerklärung, Art. 13 GDPR) and Cookies pages return 200 and contain real content (> 500 characters of text, mentions ZALF as the responsible body). | PAGE-15 to PAGE-17. |
| LEGAL-02 | MUST | Imprint and Privacy are linked from the footer of **every** inventory page (at most two clicks from anywhere). | Footer links per page. |
| LEGAL-03 | MUST | On first visit (no cookies) a cookie notice appears, can be dismissed or accepted with one click, links to the cookie/privacy page, and does not reappear after dismissal on the next page. | Fresh context on PAGE-01, then navigate. |
| LEGAL-04 | MUST | Data Policy and How to Cite pages are reachable from header and footer. | Links. |
| LEGAL-05 | MUST | Licence information is visible on dataset and document detail pages. | PAGE-04, PAGE-06. |
| LEGAL-06 | MUST | Accessibility statement exists; see A11Y-16. | Link from A11Y-16. |

---

## 7. OGC services and API

All checks are `curl` against the base URL. No authentication.

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| API-01 | MUST | WMS `GetCapabilities` returns 200 and an XML `WMS_Capabilities` document with at least one `Layer`. | `/geoserver/ows?service=WMS&request=GetCapabilities` |
| API-02 | MUST | WFS `GetCapabilities` returns 200 and XML with at least one `FeatureType`. | `/geoserver/ows?service=WFS&request=GetCapabilities` |
| API-03 | MUST | CSW `GetCapabilities` returns 200 and XML (`csw:Capabilities`); a `GetRecords` with `maxRecords=1` returns `numberOfRecordsMatched > 0`. | `/catalogue/csw?service=CSW&version=2.0.2&request=GetCapabilities` and `…&request=GetRecords&typeNames=csw:Record&resultType=results&maxRecords=1&elementSetName=brief` |
| API-04 | MUST | REST API v2 returns 200 JSON with `total > 0`: `/api/v2/resources`, `/api/v2/datasets`, `/api/v2/documents`. | `curl` plus JSON parse. |
| API-05 | MUST | Every service URL shown on `/ogc_and_api/` (PAGE-10) works as described there. | Collect URLs from the page; `curl` each. |
| API-06 | MUST | `/robots.txt` returns 200 and does not disallow `/` for all agents on production. | `curl`. |
| API-07 | SHOULD | `/sitemap.xml` returns 200 with valid XML. | `curl`. |
| API-08 | SHOULD | Dataset detail pages expose machine-readable metadata (e.g. a DataCite/ISO link or JSON-LD). | DOM of PAGE-04. |

---

## 8. Internationalisation

Languages offered: **Deutsch, English, Español, Français, Italiano**
(`settings.py`, client build `de-de, en-us, es-es, fr-fr, it-it`). German and
English are the priority languages.

| ID | Level | Requirement | How to verify |
|---|---|---|---|
| I18N-01 | MUST | The language selector is visible in the header on every page and offers the five languages. | DOM. |
| I18N-02 | MUST | Switching to **Deutsch** translates the header, footer, home page sections, catalogue UI and sign-in page. No visible English strings remain in navigation or footer (resource titles/abstracts excepted). | Switch, then visit PAGE-01, 02, 04, 07, 18; screenshot; list untranslated strings. |
| I18N-03 | MUST | No raw translation keys or template artefacts are visible in any language: e.g. `gnhome.someKey`, `{% trans`, `%(name)s`, `msgid`. | Search the visible text for those patterns. |
| I18N-04 | MUST | The chosen language persists across navigation and reloads. | Switch, navigate to two other pages, reload. |
| I18N-05 | MUST | `<html lang>` follows the chosen language (see A11Y-09). | `document.documentElement.lang`. |
| I18N-06 | SHOULD | Spot-check ES, FR and IT: header and footer are translated and no layout breaks from longer strings (wrapping in the nav, clipped buttons). | Switch; screenshot header and footer at desktop and mobile. |
| I18N-07 | SHOULD | Dates and numbers on detail pages follow the chosen locale. | PAGE-04 in DE vs EN. |

---

## 9. Performance budgets

Measure in the browser on a desktop viewport without throttling, from a fresh
context, three loads per page, report the median. Use the Performance API
(`PerformanceObserver` for `largest-contentful-paint` and `layout-shift`,
`performance.getEntriesByType('navigation'|'resource')`).

| ID | Level | Metric | Budget |
|---|---|---|---|
| PERF-01 | SHOULD | Largest Contentful Paint, PAGE-01 and PAGE-02 | ≤ 2.5 s |
| PERF-02 | SHOULD | Cumulative Layout Shift, PAGE-01 and PAGE-02 | ≤ 0.1 |
| PERF-03 | SHOULD | Time to first byte (HTML), all inventory pages | ≤ 800 ms |
| PERF-04 | SHOULD | Total transfer size, PAGE-01 (all resources) | ≤ 3 MB |
| PERF-05 | SHOULD | Largest single CSS file | ≤ 500 KB |
| PERF-06 | MUST | ORCID button click → IdP page loaded (FUNC-07) | ≤ 2 s |
| PERF-07 | SHOULD | Map viewer (PAGE-05) shows the first rendered tiles | ≤ 5 s |

Exceeding a budget by up to 20% is `WARN`; more than 20% is `FAIL` for MUST
budgets and `WARN` for SHOULD budgets. Always report the measured value.

---

## 10. Known deviations (baseline)

These were present when this spec was written (2026-10-14). Re-measure each on
every run. If it still applies, report the requirement as `KNOWN` with the
current measurement. If it no longer applies, report `PASS` and note **"baseline
item resolved: remove from §10"**. Anything failing that is not listed here is a
**new** finding.

| Ref | Requirement | Observation on 2026-10-14 | Where it comes from |
|---|---|---|---|
| K-01 | BRAND-07 | `<title>` on `/` is just the hostname `repository-e.dataservice.zalf.de`. | `geonode/templates/zalf/index.html` |
| K-02 | A11Y-09, I18N-05 | The ZALF templates (`zalf/index.html`, `faq.html`, `cms.html`, `cms_detail.html`, `trainings.html`) render `<html>` with no `lang`; `base.html` hard-codes `lang="en"` whatever language is active. | templates |
| K-03 | A11Y-01 | Navigation text `#f4f4f4` on `#4e9c18` is 3.13:1 (white on it would be 3.45:1); below 4.5:1 for normal-size nav text. Fixing it needs a design decision, e.g. a darker nav background (white on `#448615` is 4.50:1, on `#3b7a57` 5.11:1). | client `themes/zalf/less/variables.less` |
| K-04 | A11Y-01 | The highlight `#c7d406` on `#4e9c18` is 2.11:1. Acceptable only as a decorative indicator, never as text. | client theme |
| K-05 | BRAND-06 | Two sans families in use: `--zalf-font-sans` (Inter) and `--ms-font-family-base` (Montserrat, loaded by `snippets/head.html`). | `geonode/templates/geonode-mapstore-client/snippets/head.html`, client `zalf.less` |
| K-06 | API-07 | `/sitemap.xml` returns 404. | URL config |
| K-07 | A11Y-16, LEGAL-06 | No accessibility statement found in templates or client footer. | footer |
| K-08 | PERF-05 | `/static/mapstore/dist/themes/zalf.css` is about 1.2 MB uncompressed. | client theme build |

Housekeeping (not a requirement; mention once in the report if still true):
`geonode/static/geonode/css/zalf_theme.css` (palette `#0b6b7a`, `#2e7d32`) is not
referenced by any template and looks like dead code.

---

## 11. Report

Write the report to `ui-review-reports/<YYYY-MM-DD>-<host>.md` (gitignored), with
screenshots in `ui-review-reports/<YYYY-MM-DD>-<host>/`.

```markdown
# UI review: <host>, <date>

Base URL · git commit of the checkout (if run from the repo) · spec version (last commit of zalf_docs/ui_review_spec.md)

## Summary
| PASS | FAIL | WARN | KNOWN | N/A |
|---|---|---|---|---|

## New findings (not in baseline)
One bullet per FAIL/WARN: ID, one-sentence description, evidence, likely file/repo to fix.

## Resolved baseline items
K-xx that no longer apply.

## All requirements
| ID | Level | Status | Evidence |
|---|---|---|---|
```

Rules for the report:

- Every ID in §1 to §9 appears exactly once in "All requirements".
- Evidence is concrete: measured value, URL, selector, screenshot file name.
  "Looks fine" is not evidence for a FAIL or WARN.
- Group repeated instances (e.g. the same contrast failure on 18 pages) into one
  finding with a count and the list of pages.
- Where a fix location is obvious, name it (this repo vs. `geonode-mapstore-client`).

---

## Maintaining this spec

- Change the spec in the same PR that intentionally changes the look or
  behaviour it describes (new nav item, new token value, new page).
- When a baseline item is fixed, delete its row from §10 in the fixing PR.
- New pages go into §1; new external services into LINK-02 / API.
