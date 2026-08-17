#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/test.sh" \
    geonode.api.tests \
    geonode.base.api.tests \
    geonode.layers.api.tests \
    geonode.maps.api.tests \
    geonode.documents.api.tests \
    geonode.geoapps.api.tests \
    "$@"
