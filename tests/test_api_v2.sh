#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/tests/test.sh" geonode.base.api.tests geonode.layers.api.tests geonode.maps.api.tests geonode.documents.api.tests geonode.geoapps.api.tests
