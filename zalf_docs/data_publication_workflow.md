# Data Publication Workflow

## What this feature does

The data publication workflow lets designated *data stewards* formally review and publish research data in GeoNode with a citable DOI.

A **data collection** in this workflow is a **map** together with all the resources linked to it — the map layers (datasets) plus any linked documents. The map acts as the "container" that groups everything belonging to one publication.

Every data collection goes through two review steps:

```
  [Draft]  ──approve──►  [Approved]  ──publish──►  [Published + DOI]
```

1. **Approve** — a data steward confirms the collection has been internally reviewed. Nothing becomes public yet.
2. **Publish** — a data steward *manager* registers a DOI with DataCite and releases the collection. From this moment:
   - The **map** is visible to everyone (anonymous visitors and all logged-in users).
   - The **layers and documents** are visible *and downloadable* by everyone.
   - The collection has a permanent DOI (e.g. `10.20387/xxxx-xxxx`) shared by the map and all its published resources.
   - Publication dates (`date_available`, `date_issued`) are stamped automatically if not already set.
   - The original owner (the researcher) **keeps full edit rights** on their resources.

### Who can do what

| Action | Who |
|--------|-----|
| Approve a data collection | Any **member** of a data-steward group (see below), and superusers |
| Publish a data collection (register DOI) | Only **managers** of a data-steward group, and superusers |

### The buttons in the map viewer

| Button | Appears when |
|--------|-------------|
| **Approve Data Collection** (thumbs-up) | User may approve, resource is a map, and it is not yet approved |
| **Publish Data Collection** (bookmark) | User may publish, map is approved but not yet published |
| **DataCite Metadata** (download) | DataCite integration is enabled and the map is published |
| **Build / Rebuild download package** (archive) | User may publish and the map is published; shows the package state |

The publish dialog lets the steward select which linked resources to include and which DOI prefix to use. Its **Build download package after publication** checkbox, **checked by default**, queues the download package once the publication has committed.

### Download package

After publication, a map's landing page offers **Download all (ZIP, size)**: one archive with every file of the collection that anonymous visitors may download, which after publication is exactly what the publication made public. The button appears only once the package exists.

- **Contents.** Each resource's own files as GeoNode keeps them: the original upload of a dataset, the file of a document. For a dataset without an original (for example, one harvested or created before 5.x), the file comes from GeoNode's GeoServer export (WPS `gs:Download`). `MANIFEST.txt` lists every file, its resource, whether it is an original or an export, and its SHA-256.
- **Storage.** The archive is an Asset linked to the map. With `ZALF_DOWNLOAD_S3_BUCKET` set, it lives in S3-compatible object storage (Hetzner first) and downloads redirect straight to the object, so they do not cross the institute's uplink. Without it, it is a local asset.
- **Authorization.** Whoever may **view** the map may download its package. The publication grants maps view only (not download), and the package holds nothing that is not already publicly downloadable.
- **Snapshot.** The package reflects the collection when it was built. After changing a published collection, rebuild it.
- **Existing maps.** Use the steward button in the map viewer, `POST /api/v2/maps/{mapid}/download_package/`, the *Download packages* admin action, or the management command:

  ```
  python manage.py build_download_packages --all-published --missing-only   # backfill
  python manage.py build_download_packages --map 12 34 [--sync]            # selected maps
  ```

---

## Administrator guide — setting up user rights

Follow these steps to give users approve/publish rights:

### Step 1 — Create a data-steward group in GeoNode

Create a **GeoNode Group** via the web UI (*People → Groups → Create Group*), for example titled *ZALF Data Stewards*.

> ⚠️ **The slug is what counts.** GeoNode derives a URL slug from the title (e.g. `zalf_data_stewards` or `zalf-data-stewards`) and the underlying permission group is named after that slug. Check the group's page URL to see the exact slug — you will need it in step 2.
>
> Creating a plain Django group in the Django admin is **not enough**: such groups have no member/manager roles, so nobody in them could publish.

### Step 2 — Reference the group in the DataCite accounts setting

Add the group slug to the `groups` list of a DataCite account in the environment (e.g. `.devcontainer/.env` in development):

```
ZALF_DATACITE_ACCOUNTS=[{"username": "TIB.EXAMPLE", "password": "...", "groups": ["zalf_data_stewards"]}]
```

Then **restart the Django service** — the list of allowed groups is computed once at startup.

### Step 3 — Add users to the group with the right role

On the group's page (*People → Groups → your group*), add members:

- Role **Member** → may **approve** data collections.
- Role **Manager** → may **approve and publish** (register DOIs).

You can promote or demote users at any time from the group's member management page. Superusers can always approve and publish regardless of group membership.

### Common pitfalls

| Symptom | Likely cause |
|---------|-------------|
| Buttons don't appear for a user who should see them | Browser page is stale (rights are baked into the page at load — hard-refresh with Ctrl+Shift+R); or the Django container was not restarted after changing `ZALF_DATACITE_ACCOUNTS` |
| Nobody except admins can publish | The group only exists as a plain Django auth group — recreate it as a GeoNode Group and assign managers |
| A user sees Approve but not Publish | They are a plain *member*; promote them to *manager* if they should publish |
| Group configured but rights don't apply | Slug mismatch — the value in `ZALF_DATACITE_ACCOUNTS[*].groups` must equal the GeoNode group's slug exactly |
| No DOI prefixes offered in the publish dialog | The DataCite account has no prefixes assigned, credentials are wrong, or the DataCite API is unreachable (prefixes are cached for 1 hour) |

### Quick verification (Django shell)

```python
u = get_user_model().objects.get(username="steward1")
u.can_approve_data_collection()   # True for members and managers
u.can_publish_data_collection()   # True only for managers (and superusers)
settings.PUBLISH_DATA_COLLECTION_ALLOWED_GROUPS  # must contain your group slug
```

---

## Reference

### Required environment settings

```
# Required for the publication workflow to activate
RESOURCE_PUBLISHING=True        # resources start as is_published=False
ADMIN_MODERATE_UPLOADS=True     # resources start as is_approved=False

# DataCite integration
ZALF_DATACITE_BASE_URL=https://api.test.datacite.org/      # test environment
# ZALF_DATACITE_BASE_URL=https://api.datacite.org/         # production

# JSON array of DataCite accounts. Empty array disables the feature entirely.
ZALF_DATACITE_ACCOUNTS=[{"username": "ORG.PREFIX", "password": "...", "groups": ["group-slug"]}]
```

Download packages (optional; without a bucket, packages are stored locally):

```
ZALF_DOWNLOAD_S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com   # Hetzner; location = region
ZALF_DOWNLOAD_S3_REGION=fsn1
ZALF_DOWNLOAD_S3_BUCKET=bonares-download-packages
ZALF_DOWNLOAD_S3_ACCESS_KEY_ID=...                                  # SOPS-encrypted
ZALF_DOWNLOAD_S3_SECRET_ACCESS_KEY=...                              # SOPS-encrypted
ZALF_DOWNLOAD_S3_PREFIX=download-packages
ZALF_DOWNLOAD_S3_ADDRESSING_STYLE=virtual     # or path
ZALF_DOWNLOAD_S3_URL_EXPIRY=3600              # presigned URL lifetime, seconds
ZALF_DOWNLOAD_S3_PUBLIC=False                 # True: redirect to the public URL (needs a public-read bucket policy)
ZALF_DOWNLOAD_PACKAGE_BUILD_ROOT=/mnt/volumes/statics/download_packages   # scratch on a PVC, not /tmp (emptyDir)
ZALF_DOWNLOAD_PACKAGE_MAX_BYTES=53687091200   # 50 GiB
ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT=21600        # Celery time limit, seconds
ZALF_DOWNLOAD_PACKAGE_EXPORT_TIMEOUT=3600     # read timeout of one GeoServer export
```

Builds run on the Celery queue `zalf.download_package`, which the default worker consumes (it only excludes `harvesting`). Datasets that need a GeoServer export are subject to GeoServer's `download.properties` limits (`maxFeatures`, `hardOutputLimit`, raster limits); raise them for large layers.

`PUBLISH_DATA_COLLECTION_ALLOWED_GROUPS` is derived automatically from all `groups` entries across `ZALF_DATACITE_ACCOUNTS` at Django startup.

### Permission model (backend)

```python
def can_approve_data_collection(self):
    """Member (any role) of an allowed DataCite group, or superuser."""

def can_publish_data_collection(self):
    """Manager of an allowed DataCite group, or superuser."""
```

Approve and publish are authorized **solely by the group-role gate** — data stewards act on resources owned by other users, so no per-resource permission is required. Only metadata sync still needs an object-level permission:

| Operation | Authorization |
|-----------|---------------|
| Approve | `can_approve_data_collection()` (member of an allowed group) |
| Publish | `can_publish_data_collection()` (manager of an allowed group) |
| Sync metadata (POST) | `base.change_resourcebase` on the map |
| Build download package (POST) | `can_publish_data_collection()`; the map must be published |
| Download package state (GET) / file | `base.view_resourcebase` on the map |

### Frontend flags

Delivered via Django context processor → `window.__GEONODE_CONFIG__.localConfig.geoNodeSettings.datacite`:

| Key | Meaning | Controls |
|-----|---------|----------|
| `can_approve` | member (any role) of an allowed group | Approve button |
| `can_publish` | manager of an allowed group | Publish button |
| `prefixes` | DOI prefixes available to the user (only fetched for publishers) | DOI prefix selector |

These values are rendered into the page server-side — a user whose rights changed must reload the page.

### API endpoints

All under `/api/v2/`, accepting Session, Basic, and OAuth2 authentication.

#### POST `/api/v2/approve/{mapid}/`

Approve a data collection (the map and all linked resources owned by the specified owner).

**Body:** `{"owner": <user id>}` — the owner is used only to filter which linked resources to approve.

**Side effects:**
- Sets `is_approved = True` on the map and all linked resources where `resource.owner == owner`, via a direct DB update (bypassing Django signals).
- Recomputes permissions without the `approval_status_changed` flag, so the owner keeps their edit rights. No public visibility is granted at this stage.

**Errors:**

| Status | Condition |
|--------|-----------|
| 403 | Not authenticated or `can_approve_data_collection()` is False |
| 400 | `owner` field missing |
| 404 | Map or owner user does not exist |

#### POST `/api/v2/publish/{mapid}/`

Publish a data collection with DOI registration.

**Body:**
```json
{"owner": 42, "resources": [101, 102], "doi_prefix": "10.20387"}
```

**Validation order:**
1. Resources must be linked to the map, unpublished, and owned by `owner`
2. All resources must be approved
3. DOI prefix must match `^10\.\d{4,}$` and be accessible to the requesting user

**Side effects:**
1. Registers a single DOI for the whole collection (suffix = map UUID) and assigns it to the map and every selected resource
2. Sets `is_published = True` via direct DB update; stamps `date_available`, `date_issued`, `date` if unset
3. **Grants public visibility explicitly:** anonymous and registered-members groups receive `view_resourcebase` on the map, and `view_resourcebase` + `download_resourcebase` on all other resource types (datasets, documents). The owner's edit permissions are preserved.

**Errors:**

| Status | Condition |
|--------|-----------|
| 403 | Not authenticated or `can_publish_data_collection()` is False (manager role required) |
| 400 | Serializer validation failure |
| 422 | Resource not approved, DOI prefix invalid/inaccessible, or DataCite API error |
| 404 | Map or owner does not exist |

#### GET / POST `/api/v2/maps/{mapid}/download_package/`

GET returns `{state, ready, asset_id, download_url, size, sha256, built_at}`, where `state` is `null` before the first build, then `pending`, `building`, `ready` or `failed`. Data stewards also see `error`, `task_id`, `requested_by` and `updated_at`. The previous package stays downloadable while a rebuild runs.

POST queues a (re)build and returns 202. The response has `started: false` while a build is pending or running. It returns 409 for an unpublished map and 403 for anyone but data-steward managers and superusers. Both methods answer 404 if the map is not visible to the caller.

The publish endpoint accepts `"build_download_package": false` to skip the automatic build; the default is `true`.

#### GET `/api/v2/maps/{mapid}/download_package/download/`

The package itself: a redirect to the S3 object (presigned unless `ZALF_DOWNLOAD_S3_PUBLIC`), or the local file. It counts as a download of the map, and returns 404 until a package exists.

#### GET / POST `/api/v2/maps/{mapid}/sync_metadata/`

GET returns a metadata diff between the map and each linked resource (`?resource_pk=` to limit). POST syncs metadata from the map to linked resources (optional body: `resource_pk`, `field_names`); requires `base.change_resourcebase` on the map.

#### GET `/api/v2/datacite_metadata/{pk}/`

Returns DataCite XML for a resource (`application/xml`). Public endpoint. 404 if the resource or the pycsw DataCite backend is unavailable.

#### GET `/api/v2/datacite-prefixes/`

Returns `{"prefixes": [...]}` — DOI prefixes available to the authenticated user. Prefixes are fetched from the DataCite API per account and cached for 1 hour.

### DOI details

- One DOI per collection, suffix = the map's UUID (deterministic and idempotent).
- Stored as bare DOI (e.g. `10.20387/xxxx-xxxx`) without resolver prefix.
- Landing page URL is the stable `/uuid/<uuid>` link.
- Metadata XML comes from the pycsw catalogue backend, with the `<identifier>` patched to the collection DOI.
- DataCite XML generation works with **any** `CATALOGUE_ENGINE`: GeoNode bundles pycsw 3.0.0-beta1 (which includes the `datacite` output schema) and generates the record in-process against its own database. Deployments with an external pycsw (e.g. geonode-k8s with `CATALOGUE_ENGINE=pycsw_http`) therefore get full DataCite XML too — the external pycsw needs no DataCite plugin.

### Frontend plugin architecture (developers)

```
geonode-mapstore-client/client/js/plugins/
  ApproveDataCollection.jsx   — Approve button + confirm dialog (gated on can_approve)
  PublishDataCollection.jsx   — Publish button + resource checklist + DOI prefix selector + "build download package"
                                checkbox (gated on can_publish); on a published map: the download package button
  downloads/DataCiteDownload.jsx — Download DataCite XML button
client/js/hooks/useDatacitePrefixes.js — reads the datacite flags from the page config
```

All are declared `"mandatory": true` in `localConfig.json`'s `map_viewer` plugins array — required because `routes/MapViewer.jsx:selectPluginsConfig()` filters to mandatory-only entries when the map has a linked viewer configuration.

After frontend changes: rebuild the client (`npm run compile` in `geonode_mapstore_client/client`) and run `python manage.py collectstatic --noinput` in the Django container.
