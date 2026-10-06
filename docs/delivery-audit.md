# Post-publication dataset delivery audit

GeoNode owns the delivery audit because it controls the publication transition,
Guardian permissions and the authenticated GeoServer integration. The Upload
Tool may read and display the result, but it must not hold GeoServer
administrator credentials or seed GeoWebCache directly.

When a spatial dataset first becomes both approved and published, GeoNode
creates one pending audit record and enqueues the audit only after the database
transaction commits. Redelivered Celery tasks update the same one-to-one record.
Unpublished, unapproved, non-spatial and deleted datasets are skipped safely.

The owner or a staff user can read the latest machine-readable result:

```text
GET /api/v2/datasets/<id>/delivery-audit/
```

The same users can explicitly request a new audit with `POST`. A request is
rejected while an audit is pending/running or while the dataset is not both
approved and published.

## Checks

The task compares anonymous Guardian permissions with exact-layer GeoFence
rules; checks the GeoServer layer; validates the GWC gridset, 512-pixel tile,
2x2 metatile, format and `STYLES` parameter filter; and performs anonymous WMS
and WFS requests. The WMS request is aligned to the configured grid and is only
accepted when its response is an image with
`geowebcache-cache-result: HIT|MISS`. HTTP 200 exception XML is a failure.

For vector layers the task reports the source SRID, reprojection requirement,
GiST/SP-GiST geometry index, PostgreSQL analyze timestamps and estimated rows.
Geometry complexity is sampled from at most 1,000 non-null geometries; the audit
does not execute a full-table render or exact full-table vertex count.

## Configuration

The defaults match the ZALF MapStore/GWC contract:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ZALF_DELIVERY_AUDIT_GRIDSET` | `EPSG:3857x2` | Required client gridset |
| `ZALF_DELIVERY_AUDIT_FORMAT` | `image/png8` | Cached WMS format |
| `ZALF_DELIVERY_AUDIT_TILE_SIZE` | `512` | `EPSG:3857x2` tile width and height |
| `ZALF_DELIVERY_AUDIT_META_FACTOR` | `2` | Expected metatile width/height |
| `ZALF_DELIVERY_AUDIT_TILE_ZOOM` | `7` | Aligned audit tile zoom |
| `ZALF_DELIVERY_AUDIT_GEOMETRY_SAMPLE` | `1000` | Maximum sampled geometries |
| `ZALF_DELIVERY_AUDIT_REQUEST_TIMEOUT` | `60` | Per-request timeout in seconds |

## Optional bounded seed

Automatic seeding is disabled by default:

```text
ZALF_DELIVERY_AUDIT_SEED_ENABLED=False
```

If an operator opts in, the seed runs only after every audit check passes. It
uses the dataset extent and configured grid/format, one thread, zoom range
`0..7`, a maximum estimated budget of 500 tiles, and the task's five-minute
hard timeout. These bounds are configured with
`ZALF_DELIVERY_AUDIT_SEED_MIN_ZOOM`,
`ZALF_DELIVERY_AUDIT_SEED_MAX_ZOOM`, and
`ZALF_DELIVERY_AUDIT_SEED_MAX_TILES`. Requests over budget are refused rather
than partially submitted.

The task never writes an SLD, adds `MaxScaleDenominator`, or creates a
generalized table/view. Those are per-layer cartographic decisions and require
an explicit reviewed performance profile such as the dataset 2074 Helm profile.
