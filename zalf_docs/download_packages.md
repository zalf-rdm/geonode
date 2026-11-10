# Download packages

One ZIP per published data collection, holding every file of the collection that
anonymous visitors may download. Built by a Celery task, stored as an Asset on
the map, and served from S3-compatible object storage so the bytes never cross
the institute's uplink.

Upstream GeoNode offers no download for a map at all (`DownloadArrayLinkField`
returns `[]`), so researchers had to click through one download per layer and per
document. This feature replaces that, and replaces the custom Java WPS process
sketched in zalf-rdm/geonode#659: building is Python and Celery only.

Part of the [data publication workflow](data_publication_workflow.md) — a map is
the container of a publication, and its package is what the publication made
public. See also the change-log row in
[`upstream_divergences.md`](upstream_divergences.md).

**Contents**

- [What a visitor sees](#what-a-visitor-sees)
- [What goes into a package](#what-goes-into-a-package)
- [How a package comes to exist](#how-a-package-comes-to-exist)
- [Storage](#storage)
- [Authorization](#authorization)
- [The activation switch](#the-activation-switch)
- [Configuration](#configuration)
- [Management commands](#management-commands)
- [API endpoints](#api-endpoints)
- [Django admin](#django-admin)
- [Validation](#validation)
- [Inspecting the bucket with s3cmd](#inspecting-the-bucket-with-s3cmd)
- [Operations and troubleshooting](#operations-and-troubleshooting)

---

## What a visitor sees

After publication, a map's landing page offers **Download all (ZIP, size)**. The
button appears only once a package exists; there is no placeholder and no
disabled button, because a map has no other download links to offer.

Data stewards additionally get **Build download package** / **Rebuild download
package** in the map viewer's **Edit** dropdown, in the slot the Publish button
uses before publication. It shows the package state and polls every 10 s while a
build is pending or running.

## What goes into a package

Every resource linked to the map that **anonymous visitors may download** —
which, after publication, is exactly what the publication made public. A
resource restricted again later stays in the package until the next rebuild.

Files come from what GeoNode already keeps:

| source | used for |
|---|---|
| the resource's own `LocalAsset` | the importer's original upload of a dataset, a document's file |
| GeoNode's GeoServer export (WPS `gs:Download`) | only datasets with no original file, e.g. harvested or created before 5.x |

Layout inside the ZIP:

```
datasets/<pk>-<slug>/<original files>
documents/<pk>-<slug>/<file>
MANIFEST.txt
```

`MANIFEST.txt` records, per file: its path in the archive, the resource it came
from, its title, whether it is an original or an export, its size and its
SHA-256. The collection DOI is in the header.

A build that would produce an empty package fails instead, and one that would
exceed `ZALF_DOWNLOAD_PACKAGE_MAX_BYTES` fails rather than filling the volume.

## How a package comes to exist

| trigger | who | when |
|---|---|---|
| the publish endpoint | the publishing steward | automatically, unless the dialog's *Build download package after publication* checkbox is cleared |
| **Build / Rebuild** in the map viewer | data stewards, superusers | published maps only |
| `POST /api/v2/maps/<id>/download_package/` | data stewards, superusers | published maps only |
| *Download packages* → **Rebuild the download package** | admin users | any selected row |
| [`manage.py build_download_packages`](#build_download_packages) | operators | backfill, or one map |

Publication queues the build with `transaction.on_commit`, so the task starts
only after the public permissions have been written — otherwise it would package
the pre-publication permissions and produce an empty archive.

Only one build per map runs at a time. A row left in `building` by a worker that
died may be restarted once the task's time limit has passed; until then a new
request answers `started: false`. A rebuild links the new asset **before**
deleting the old one, so a working download is never interrupted.

## Storage

The archive is an `Asset` linked to the map, plus a `Link` so it appears among
the map's links.

- **With `ZALF_DOWNLOAD_S3_BUCKET` set** (production): an `S3Asset`, handled by
  `S3AssetHandler` — new in this fork, since GeoNode ships only
  `LocalAssetHandler` whose storage is hard-wired to the filesystem. Downloads
  answer 302 to a presigned URL (or the public object URL with
  `ZALF_DOWNLOAD_S3_PUBLIC`), so the bytes go from the provider straight to the
  browser.
- **Without a bucket** (the dev default): a GeoNode `LocalAsset` on the media
  volume, served by GeoNode itself.

The handler is configured **only** by `ZALF_DOWNLOAD_S3_*`, never the global
`AWS_*` settings, so it cannot interfere with GeoNode's other storage. Each
upload gets a fresh key (`<prefix>/<uuid>/<map-slug>-<map-pk>.zip`), so a
rebuild never overwrites the object still being served. Objects are stored with
`Content-Type: application/zip` and an `attachment` content disposition, which
is what makes the browser save the file under its proper name after the
redirect.

## Authorization

Whoever may **view** the map may download its package.

This is deliberately looser than GeoNode's own asset endpoint, which requires
`download_resourcebase` on the linked resource — the publication grants maps
`view` only, and granting download on maps instead would change publication
semantics and require re-permissioning every published map. It is safe because a
package only ever contains files that are already publicly downloadable.

| operation | authorization |
|---|---|
| build / rebuild (POST) | `can_publish_data_collection()`; the map must be published |
| state (GET) and the file | `base.view_resourcebase` on the map |

## The activation switch

`ZALF_DOWNLOAD_PACKAGE_ENABLED` (default `True`) takes the whole feature out of
use. Every entry point checks it:

| entry point | with the switch off |
|---|---|
| publication | queues nothing, and reports no `download_package` |
| `POST …/download_package/` | 409 with a reason |
| `GET …/download_package/` | 200 with `enabled: false` and an empty state |
| `GET …/download_package/download/` | 404, even for a package built earlier |
| the admin rebuild action | a warning; nothing queued |
| `build_download_packages` | `CommandError` |
| `download_package_status` | still reports, with a note that the feature is off |
| `validate_download_packages` | still validates, with the same note |
| the client | hides the publish checkbox, the steward button and the ZIP link |

Packages already built are **kept, not deleted**, so switching it back on makes
them available again. The `S3AssetHandler` registration and the Celery queue
stay in place while it is off, so earlier packages remain resolvable (the asset
admin, deleting a map) and in-flight tasks can drain. A build queued *before*
the switch was flipped is recorded as **failed** rather than left pending, which
would block the next request until the task's time limit.

## Configuration

Optional as a whole: without a bucket, packages are stored locally.

```
ZALF_DOWNLOAD_PACKAGE_ENABLED=True            # the switch for the whole feature

# --- Object storage ---
ZALF_DOWNLOAD_S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com   # Hetzner; location = region
ZALF_DOWNLOAD_S3_REGION=fsn1
ZALF_DOWNLOAD_S3_BUCKET=bonares-download-packages
ZALF_DOWNLOAD_S3_ACCESS_KEY_ID=...                                  # SOPS-encrypted
ZALF_DOWNLOAD_S3_SECRET_ACCESS_KEY=...                              # SOPS-encrypted
ZALF_DOWNLOAD_S3_PREFIX=download-packages
ZALF_DOWNLOAD_S3_ADDRESSING_STYLE=virtual     # or path
ZALF_DOWNLOAD_S3_URL_EXPIRY=3600              # presigned URL lifetime, seconds
ZALF_DOWNLOAD_S3_PUBLIC=False                 # True: redirect to the public URL (needs a public-read bucket policy)

# --- Building ---
ZALF_DOWNLOAD_PACKAGE_BUILD_ROOT=/mnt/volumes/statics/download_packages   # scratch on a PVC, not /tmp (emptyDir)
ZALF_DOWNLOAD_PACKAGE_MAX_BYTES=53687091200   # 50 GiB
ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT=21600        # Celery time limit, seconds
ZALF_DOWNLOAD_PACKAGE_EXPORT_TIMEOUT=3600     # read timeout of one GeoServer export
```

Notes that have bitten us:

- **`ZALF_DOWNLOAD_PACKAGE_BUILD_ROOT` must be on a PVC.** `/tmp` is an
  `emptyDir` in the geonode-k8s chart, and a multi-GB build there risks evicting
  the pod.
- **Empty `ZALF_DOWNLOAD_S3_ENDPOINT_URL` means AWS S3 itself**, not "no S3"; it
  is `ZALF_DOWNLOAD_S3_BUCKET` that decides local versus object storage.
- **`ZALF_DOWNLOAD_S3_PUBLIC=True` needs a bucket policy**, not a canned ACL:
  the handler sets no ACL, because support for them varies across S3-compatible
  providers.
- Every variable is commented in `geonode/settings.py`; this table is the
  deployment view of the same block.

## Management commands

Three commands, answering three different questions.

| command | question | asks |
|---|---|---|
| [`build_download_packages`](#build_download_packages) | make them exist | builds |
| [`download_package_status`](#download_package_status) | what did the builds conclude? | the database |
| [`validate_download_packages`](#validate_download_packages) | what can visitors actually download? | the storage |

All three run as `python manage.py <command>`; in a container, that is
`docker exec <django container> python manage.py <command>`.

### `build_download_packages`

Builds, or rebuilds, the package of published data collections. Queues a Celery
task per map unless `--sync` is given. Declines with a `CommandError` while the
feature is switched off.

| option | meaning |
|---|---|
| `--map ID [ID …]` | these maps only. Unknown or unpublished IDs are reported on stderr and skipped |
| `--all-published` | every published map |
| `--missing-only` | with `--all-published`: skip maps whose package is already `ready` |
| `--sync` | build in this process instead of queuing. No worker needed; blocks until done |

One of `--map` or `--all-published` is required. There is **no `--rebuild`
flag**: building a map that already has a package *is* the rebuild.

```bash
# backfill everything that has no package yet
manage.py build_download_packages --all-published --missing-only

# rebuild two collections
manage.py build_download_packages --map 12 34

# build one in the foreground, e.g. to watch it fail
manage.py build_download_packages --map 12 --sync
```

Output is one line per map: `Map 12: queued`, `Map 12: already building`, or
with `--sync` the resulting state and error.

### `download_package_status`

Lists every published map with the build state recorded in the database:
`missing` (no package row), `pending`, `building`, `ready` or `failed`. Keeps
working while the feature is switched off, and says so.

| option | meaning |
|---|---|
| `--missing` | only maps without a ready package — the set `--missing-only` would build |
| `--state STATE [STATE …]` | only maps in these states (`missing`, `pending`, `building`, `ready`, `failed`) |
| `--errors` | print the last line of each failed build's error |

```bash
manage.py download_package_status
manage.py download_package_status --state failed --errors
```

A `ready` row here means *the last build said it succeeded*. It does **not**
mean the file is still there — that is what the next command is for.

### `validate_download_packages`

Checks each package against its storage. See [Validation](#validation) for what
each status means.

| option | meaning |
|---|---|
| `--map ID [ID …]` | these maps only |
| `--broken-only` | print only the rows needing attention; the summary still counts everything |
| `--missing` | also list published collections with no package at all |
| `--deep` | download each package, read its ZIP and compare its sha256 with the build's |
| `--max-deep-bytes N` | with `--deep`, skip packages larger than N bytes (default 2 GiB) |
| `--orphans` | also list objects under the prefix that no asset references, and package assets no row references |
| `--fail-on-broken` | exit 1 if anything is broken, for cron and monitoring |

```bash
manage.py validate_download_packages                        # the report
manage.py validate_download_packages --broken-only --missing
manage.py validate_download_packages --deep                 # verify checksums
manage.py validate_download_packages --orphans              # leaked objects
manage.py validate_download_packages --fail-on-broken       # cron
```

Checks are read-only: nothing here builds, deletes or rewrites. Rebuild whatever
it flags with `build_download_packages --map <ID>`.

## API endpoints

Under `/api/v2/`, accepting Session, Basic and OAuth2 authentication. Both
answer 404 if the map is not visible to the caller.

### `GET / POST /api/v2/maps/{mapid}/download_package/`

**GET** returns `{enabled, state, ready, asset_id, download_url, size, sha256,
built_at}`. `state` is `null` before the first build, then `pending`,
`building`, `ready` or `failed`. Data stewards also see `error`, `task_id`,
`requested_by` and `updated_at`. The previous package stays downloadable while a
rebuild runs.

`enabled` is `false` while the feature is switched off, with an empty state; the
client hides its buttons on that.

**POST** queues a (re)build and returns 202, with `started: false` while a build
is already pending or running.

| status | condition |
|---|---|
| 403 | not a data-steward manager or superuser |
| 409 | the map is not published, or the feature is switched off |
| 404 | the map is not visible to the caller |

### `GET /api/v2/maps/{mapid}/download_package/download/`

The package itself: 302 to the S3 object (presigned unless
`ZALF_DOWNLOAD_S3_PUBLIC`), or the local file. Counts as a download of the map.
404 until a package exists, and while the feature is switched off.

### `POST /api/v2/publish/{mapid}/`

Takes `"build_download_package": false` to skip the automatic build; the default
is `true`. The response carries `"download_package": "queued"` when one was
queued. Documented in full in
[data_publication_workflow.md](data_publication_workflow.md#post-apiv2publishmapid).

## Django admin

Under **Zalf → Download packages**. Rows are read-only: a package is created by
building one, never by hand.

| | |
|---|---|
| the changelist | map, state, size, built at, updated at; filter by state, search by map title |
| **Rebuild the download package** (action) | queues a build per selected row; warns and queues nothing while the feature is off |
| **Validate the stored package** (action) | checks the selected rows and reports each as a message |
| **Validate storage** (button) | the full report page, `/admin/zalf/downloadpackage/validation/` |

The validation page checks every package, links each row to its package, and has
buttons for the deep check and the orphan listing. Validation deliberately never
runs on the changelist itself: one request per row to the bucket would make the
list as slow as the bucket is far away, and unusable when it cannot be reached.

**Zalf → S3 assets** lists the stored objects themselves — bucket, key, size
and owner — and is where a dangling asset is removed; deleting a row there
removes the object from the bucket too. Rows are read-only otherwise: one
describes a stored object, so a build writes it, not a person. (GeoNode registers
only `LocalAsset`, so this admin is part of the fork.)

## Validation

A `DownloadPackage` row records what its last build *concluded*. It cannot say
whether the file is still there: a bucket lifecycle rule, a manual `s3cmd del`,
a delete that failed (which is only logged, since an orphan beats a failed
delete) or a restored database all leave a row saying `ready` while the download
is 404 — or, worse, truncated.

`geonode/zalf/download_package_checks.py` asks the storage instead, and is the
single implementation behind both the command and the admin page, so the two
cannot disagree.

Statuses, least to most urgent:

| status | means |
|---|---|
| `ok` | the object is there and its size matches the build. With `--deep`, its ZIP reads and its sha256 matches too. A note is added, without failing the check, if the content type is not `application/zip` or the attachment disposition is missing |
| `pending` | a build is queued or running. Not a fault |
| `missing` | a published collection that never had a package (`--missing` only). Build it with `build_download_packages --missing-only` |
| `stale` | still `pending`/`building` past `ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT`: the worker died. A rebuild may be requested |
| `failed` | the build itself failed; the last line of its error is shown |
| `no-asset` | the row says `ready` but no asset is linked — the asset was deleted under it |
| `mismatch` | the stored size differs from what the build recorded, the object is empty, or (`--deep`) the sha256 differs |
| `corrupt` | `--deep`: not a readable ZIP, or a member fails its CRC — which is what catches a truncated upload that still has a valid central directory |
| `gone` | the object or file is not there at all |
| `unreachable` | the storage could not be asked: wrong credentials, wrong endpoint, network. Counted as broken, because downloads are failing for visitors too |

Everything from `stale` down counts as broken for `--fail-on-broken` and for the
admin page's warning.

`--orphans` covers the other direction: objects under the configured prefix that
no asset references, and package assets that no `DownloadPackage` row
references. Both are bytes the bucket is charging for that nothing will ever
serve.

Checks use a client with a 5 s connect and 15 s read timeout and two attempts
(`s3_client(for_check=True)`), so a wrong endpoint fails in seconds rather than
the default minute per attempt.

## Inspecting the bucket with s3cmd

GeoNode never serves the ZIPs itself, so `s3cmd` is the way to see what is
actually stored.

**Configure.** Write a config of its own rather than `~/.s3cfg`, so it does not
collide with other buckets:

```ini
# ~/.s3cfg-packages   (chmod 600)
[default]
access_key = <ZALF_DOWNLOAD_S3_ACCESS_KEY_ID>
secret_key = <ZALF_DOWNLOAD_S3_SECRET_ACCESS_KEY>
host_base = fsn1.your-objectstorage.com
host_bucket = %(bucket)s.fsn1.your-objectstorage.com
bucket_location = fsn1
use_https = True
signature_v2 = False
human_readable_sizes = True
```

`host_base`/`host_bucket` are `ZALF_DOWNLOAD_S3_ENDPOINT_URL` without the scheme
and `bucket_location` is `ZALF_DOWNLOAD_S3_REGION`, so adjust both for another
region or provider. Keep the `%(bucket)s` placeholder — hardcoding a bucket name
there pins the config to that single bucket. With
`ZALF_DOWNLOAD_S3_ADDRESSING_STYLE=path`, drop the `%(bucket)s.` prefix instead.

The two keys are the ones from the SOPS-encrypted env, not the global `AWS_*`
credentials. Against a running stack they can be read from the container:

```bash
docker exec <django container> printenv ZALF_DOWNLOAD_S3_ACCESS_KEY_ID
docker exec <django container> printenv ZALF_DOWNLOAD_S3_SECRET_ACCESS_KEY
```

**Use.** `$B` below is
`s3://<ZALF_DOWNLOAD_S3_BUCKET>/<ZALF_DOWNLOAD_S3_PREFIX>`:

```bash
alias s3p='s3cmd -c ~/.s3cfg-packages'
B=s3://bonares-download-packages/download-packages

s3p ls --recursive "$B/"                    # every package, with size and build time
s3p du "$B/"                                # total space the packages take up
s3p info "$B/<uuid>/<slug>.zip"             # size, MD5, content-type, content-disposition
s3p get "$B/<uuid>/<slug>.zip"              # download one to inspect it
s3p signurl "$B/<uuid>/<slug>.zip" +3600    # presigned URL, as the API hands out
```

One object per package, keyed `<prefix>/<uuid>/<map-slug>-<map-pk>.zip`, where
the UUID is the asset's.

> **Deleting with `s3cmd` leaves the database behind.** The `DownloadPackage`
> row and the `Asset` still point at the gone object, and the API keeps
> reporting the package as `ready` until something tries to serve it —
> `validate_download_packages` reports it as `gone`. Remove packages through the
> Django admin (S3 assets, which deletes the object too) or rebuild them with
> `build_download_packages --map <ID>`, and reach for `s3cmd del` only for
> orphans that no asset references any more.
> `validate_download_packages --orphans` is what lists those.

## Operations and troubleshooting

**Celery.** Builds run on the queue `zalf.download_package`, which exists so a
long build can be moved to a dedicated worker. The default worker consumes it as
long as `celery-cmd` only excludes `harvesting`, so no extra worker is needed
out of the box.

**GeoServer.** Datasets that need an export are subject to GeoServer's
`download.properties` limits (`maxFeatures`, `hardOutputLimit`, raster limits).
Raise them for large layers, or the export fails and the build fails with it.

| symptom | likely cause |
|---|---|
| build fails with *no publicly downloadable files* | the linked resources are not published, only the map is. The package holds what the publication made public |
| the row sits in `building` forever | the worker died. After `ZALF_DOWNLOAD_PACKAGE_TIME_LIMIT` it may be rebuilt; `validate_download_packages` reports it as `stale` |
| the state endpoint answers `enabled: false` | `ZALF_DOWNLOAD_PACKAGE_ENABLED` is off in that environment |
| the download 404s although the state is `ready` | the object is gone. `validate_download_packages` says `gone`; rebuild it |
| the browser saves the ZIP under a random name | the object has no `attachment` content disposition — it was not uploaded by this handler. Rebuild it |
| the build fails on upload against a non-AWS provider | boto3 ≥ 1.36 sends CRC checksums by default and some providers reject them. The handler sets `when_required`; check it has not been overridden |
| `unreachable` for everything | credentials or endpoint. `s3cmd info` with the same values will say which |
| the pod is evicted mid-build | `ZALF_DOWNLOAD_PACKAGE_BUILD_ROOT` points at `/tmp`, which is an `emptyDir` |

**Monitoring.** `validate_download_packages --fail-on-broken` is meant for
cron: it exits 1 when anything is broken, and `unreachable` counts as broken
because visitors' downloads are failing too.

---

## Implementation map (developers)

| file | holds |
|---|---|
| `geonode/zalf/download_packages.py` | building: resource selection, export fallback, the ZIP, `MANIFEST.txt`, `request_build`, `run_build`, `is_enabled` |
| `geonode/zalf/download_package_checks.py` | validation: `check_package`, `check_packages`, `find_orphans`, `find_dangling_assets` |
| `geonode/zalf/s3_assets.py` | `S3AssetHandler`, `S3AssetDownloadHandler`, `s3_client` |
| `geonode/zalf/models.py` | `DownloadPackage`, `S3Asset` |
| `geonode/zalf/tasks.py` | the Celery task |
| `geonode/zalf/api/download_package_views.py` | the two endpoints |
| `geonode/zalf/admin.py` | the changelist, both actions, the validation page |
| `geonode/templates/zalf/admin/` | the changelist override and the validation page |
| `geonode/zalf/tests/test_download_packages.py` | the whole feature, 70 tests |

Client side (`geonode-mapstore-client`):
`js/plugins/PublishDataCollection.jsx` (the dialog checkbox and the steward
button), `themes/zalf/utils/DownloadPackageUtils.js`,
`themes/zalf/components/content/DatasetLandingPage.jsx` (the ZIP link), and the
`PublishDataCollection` entries in `static/mapstore/configs/localConfig.json`.
