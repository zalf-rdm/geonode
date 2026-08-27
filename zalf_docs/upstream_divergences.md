# ZALF GeoNode vs. upstream GeoNode

This is the map of where `zalf-rdm/geonode` deliberately differs from `GeoNode/geonode`.
It exists so that an upstream merge is a review rather than an archaeology exercise: when a
merge conflicts, this page should tell you *why* our side looks the way it does.

**Keep this file up to date.** Any change to `zalf-rdm/geonode` that adds, removes or alters
a divergence from upstream belongs here, in the same PR as the change.

> Reference point: the current fork base is upstream commit `7a6c46e44` (2025-11-11),
> i.e. GeoNode 5.0.3. Update this line when the fork is rebased or a new upstream release
> is merged.

---

## How the divergences are organised

There are three kinds, and the distinction matters when resolving a merge:

| Kind | Merge strategy |
|---|---|
| **Additive** — new files upstream does not have (`geonode/zalf/`, `zalf_docs/`, …) | Never conflicts. Keep ours. |
| **Configured** — upstream code driven by ZALF settings/env | Prefer upstream code, re-check our env defaults still make sense. |
| **Patched** — upstream files edited in place | The risky ones. Each is listed below with its reason; re-apply deliberately. |

---

## 1. The `geonode.zalf` app (additive)

`geonode/zalf/` is entirely ours, registered via `INSTALLED_APPS += ("geonode.zalf",)`
([settings.py:2390](../geonode/settings.py#L2390)). `UploadAppConfig.run_setup_hooks()` is the
single wiring point — URL patterns, template-dir priority, DataCite config warnings and the
catalogue signals all attach from there.

| Module | Purpose |
|---|---|
| `api/datacite.py` | DOI registration against DataCite; see [data_publication_workflow.md](data_publication_workflow.md) |
| `api/cms_*.py`, `models.py` | Lightweight CMS (highlighted cases, spotlight banners) for the landing page |
| `catalogue.py` | ISO scope codes — see §4 |
| `signals.py` | Catalogue signal wiring — see §4 |
| `templatetags/zalf_iso.py` | Exposes the scope codes to the ISO XML template |
| `management/commands/zalf_sync_csw_scope.py` | Backfills scope codes into existing records |

## 2. BonaRes metadata model (patched — `geonode/base/models.py`)

The fork adds seven models to `geonode.base` for DataCite/BonaRes-grade metadata:

`RelatedIdentifierType`, `RelationType`, `ResourceTypeGeneral`, `RelatedIdentifier`,
`Organization`, `Funding`, `RelatedProject`.

These are surfaced through a custom metadata handler, `geonode.metadata.handlers.zalf.ZalfHandler`,
registered in [metadata/settings.py](../geonode/metadata/settings.py) alongside the upstream handlers,
with its own JSON schema at `geonode/metadata/schemas/zalf.json`. `JSONSCHEMA_BASE` also points
at that schema rather than upstream's.

**Merge note:** upstream changes to `MetadataHandler` interfaces ripple into `zalf.py`.

## 3. ORCID-only login (configured + patched)

Driven by `SOCIALACCOUNT_ONLY`, with ORCID brokered through Keycloak via allauth's
`openid_connect`. Full detail in [orcid_only_login.md](orcid_only_login.md). Touches
`geonode/people/` (profile model gains `orcid_identifier`, profile extractor) and several
templates.

## 4. Catalogue / CSW (patched)

The most heavily diverged area, and the one to read carefully on merge.

### 4.1 Service metadata (`settings.py`)

`PYCSW["CONFIGURATION"]["metadata"]` carries ZALF identification, provider, contact and a
filled-in INSPIRE block, all `os.getenv`-driven from `PYCSW_*` variables so the values live in
the environment rather than in code. Upstream ships placeholders (`"Organization Name"`,
`"YYYY-MM-DD"`); do not let a merge reintroduce them.

INSPIRE specifics worth knowing:
- `languages_supported` uses ISO 639-2/B (`ger`, `eng`).
- `gemet_keywords` must be exact GEMET "INSPIRE themes" labels — pycsw stamps them
  `inspire_common:inspireTheme_eng`, so free text will not validate.
- `temp_extent` needs **both** bounds: pycsw writes `StartingDate` and `EndDate`
  unconditionally, so an open-ended extent cannot be expressed.
- `PYCSW_INSPIRE_DATE` and `PYCSW_INSPIRE_TEMP_EXTENT_END` are manual — bump them when the
  block changes.

### 4.2 Which resources the CSW exposes

```python
PYCSW["FILTER"] = ast.literal_eval(os.getenv("PYCSW_FILTER", "{'resource_type__in': ['dataset', 'map']}"))
```

Upstream's `GeoNodeRepository.query()` falls back to datasets only, which hides maps from
harvesters entirely.

### 4.3 ISO scope codes (issue #707)

FAIRagro harvests our CSW and needs to tell maps from datasets from tables:

| Resource | `gmd:MD_ScopeCode` |
|---|---|
| Map (including `tabular-collection`) | `series` |
| Dataset with `subtype="tabular"` | `nonGeographicDataset` |
| Everything else | `dataset` |

The code lives in `geonode/zalf/catalogue.py` and reaches **two** places that must agree:

1. the stored `metadata_xml` (what pycsw dumps verbatim for `elementsetname=full`), via the
   `zalf_iso` template tags in `catalogue/zalf_metadata.xml`;
2. the **`csw_type` column**, which backs `dc:type`, the `apiso:Type` queryable harvesters
   filter on, and `hierarchyLevel` in brief/summary records.

Also in the template:
- **The series lists its members, not the other way round.** A map's record carries one
  `gmd:aggregationInfo/MD_AggregateInformation` per published member dataset, holding the
  member UUID in `aggregateDataSetIdentifier` with `associationType=crossReference`. Dataset
  records are left completely untouched — no `gmd:parentIdentifier`.

  The reason is cardinality: a dataset can belong to several maps, while ISO allows exactly
  one `parentIdentifier`, so a child-side link would have to pick one map arbitrarily and go
  stale for the rest. `aggregationInfo` is `0..n`, so the series side represents the real
  many-to-many shape. It sits between `resourceConstraints` and `spatialRepresentationType`
  in the `AbstractMD_Identification` sequence.

  On the association type: ISO 19115-1 has a precise `isComposedOf`, but these records cite
  the 2005 gmxCodelists `DS_AssociationTypeCode`, which has no whole-to-part value —
  `crossReference` is its generic one. Change `SERIES_ASSOCIATION_TYPE` in
  `geonode/zalf/catalogue.py` if a harvester needs something else.
- The geographic extent is suppressed for `nonGeographicDataset`, because the datapackage
  importer assigns every tabular dataset a placeholder world bbox.

`geonode/zalf/signals.py` connects upstream's `catalogue_post_save` / `catalogue_pre_delete`
for `Map` (upstream wires only `Dataset` and `Document`), keeps `csw_type` in sync, and — since
the dependency runs member → series — regenerates a dataset's owning maps whenever it is saved
or deleted. The delete case needs a `pre_delete` stash: `MapLayer.dataset` is
`on_delete=SET_NULL`, so by `post_delete` the link is already gone.

Backfill existing records with `manage.py zalf_sync_csw_scope` (supports `--dry-run`,
`--type`, `--id`).

### 4.4 ISO XML template

`geonode/catalogue/templates/catalogue/zalf_metadata.xml` is a ZALF fork of upstream's
`full_metadata.xml`, selected via `CATALOG_METADATA_TEMPLATE`. Differences: GDI-DE compliant
role labels (`geonode/catalogue/templatetags/gdi_de.py`), multi-valued contact roles,
`LanguageCode` elements instead of plain strings, a URI-form CRS code, and the scope-code work
above.

### 4.5 pycsw queryable mappings

`pycsw_local_mappings.py` repoints two queryables away from raw related managers, because
pycsw assigns queryables straight into XML and chokes on non-strings:

| Queryable | Points at | Why |
|---|---|---|
| `pycsw:Contacts` | `ResourceBase.csw_contacts()` | was a `ManyRelatedManager`; broke the DataCite output schema (#724) |
| `pycsw:Publisher` | `ResourceBase.publisher_csv` | was a list of Profiles; broke *every* GetRecords response as soon as a matched resource had a publisher |

Unpublished resources are excluded in `GeoNodeRepository._get_repo_filter()` rather than in the
default `PYCSW["FILTER"]`, so a deployment overriding that setting cannot accidentally expose
them (#706).

## 5. Metadata editor saves the concrete instance (patched)

[metadata/api/views.py](../geonode/metadata/api/views.py) — the view holds a bare `ResourceBase`
(`ResourceBase.objects` is *not* a polymorphic manager), while `metadata_manager` rebinds to
`get_real_instance()` internally. Django matches `post_save` receivers on the exact sender
class, so upstream's `resource.save()` only ever fired `sender=ResourceBase` receivers — never
the `sender=Dataset/Document/Map` ones that regenerate the catalogue XML. Every metadata edit
was therefore invisible over CSW. We save `resource.get_real_instance()` instead.

## 6. Tabular / non-spatial data (patched)

Companion to the `contrib_datapackage` importer, which stamps imported tables with
`subtype="tabular"`:

- `Map` gains subtype `tabular-collection` when all its layers are tabular
  ([maps/api/views.py:118](../geonode/maps/api/views.py#L118)).
- WFS links and a proper `download_url` for tabular datasets; GWC calls skipped for
  non-spatial data.

## 7. Operational and UI additions (mostly additive)

- **Landing pages / institutional templates** — `geonode/templates/` (imprint, privacy,
  data policy, how-to-cite, publications, …) and a `zalf/` template tree.
- **AGROVOC importer** — `geonode/base/management/commands/geonode-agrovoc-importer`.
- **GWC management command** — `geonode/geoserver/management/commands/gwc.py`.
- **Upload validation** — `geonode/upload/zip_validation.py`, `geonode/documents/validation.py`.
- **LDAP, Sentry, Slack** settings blocks.
- **CI** — `.github/workflows/checks.yml` plus per-version Docker publish workflows.

---

## Known limitations

- **Person/profile edits do not regenerate catalogue XML.** Contact details
  (`individualName`, `organisationName`, e-mail, …) are baked into each resource's stored
  `metadata_xml` at generation time. Editing a `Profile` updates no resource, so every ISO
  record referencing that person keeps the old details until something else triggers a
  regeneration. Accepted for now; `manage.py zalf_sync_csw_scope` re-renders everything if a
  bulk refresh is needed.
- **Series membership is not queryable.** The member UUIDs live in the series record's XML
  body only; there is no pycsw queryable for `gmd:aggregationInfo`, so harvesters cannot
  filter on it. They can read it out of the record.
- **Saving a dataset costs one CSW dispatch per owning map**, because the map's record embeds
  its member list. Fine at current volumes; move to Celery if dataset saves get slow.
- **`csw_wkt_geometry` still holds the world bbox for tabular datasets**, so CSW bbox queries
  keep matching them even though their ISO record no longer advertises an extent.
- **`layer.restriction_code_type` does not exist on any model** (the field is
  `restriction_code`). The `{% if %}` guarding the resource-constraints block in
  `zalf_metadata.xml` is therefore always false, and access constraints never appear in ISO
  records. Django templates swallow the `AttributeError`. Not yet fixed.
- **Child tables carry shadow translation columns.** `maps_map`, `layers_dataset` and
  `documents_document` each have `*_en` columns for six fields inherited from `ResourceBase`,
  because each child's `translation.py` registers inherited fields while
  `base/translation.py` registers `ResourceBase` with none. `Map.objects` reads the shadow
  copy, `ResourceBase.objects` reads `base_resourcebase`. This is upstream behaviour and
  normal writes keep both in sync — but code that writes through the bare parent and then
  saves the child will revert the write.
- **`sparse_field_registry` is a module-level singleton** that tests register into and never
  clean up, so sparse fields leak between tests in a process. A test doing a full metadata
  `PUT` will fail on unrelated registered fields; use `PATCH` instead.
