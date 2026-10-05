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
