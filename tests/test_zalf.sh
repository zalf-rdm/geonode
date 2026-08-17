#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ZALF fork-specific tests. `geonode.zalf` is attached via `INSTALLED_APPS += ("geonode.zalf",)`
# rather than being part of GEONODE_APPS, so the upstream suite selection (which iterates
# settings.GEONODE_APPS) never picks it up. Without this suite the fork's own code is untested.

"$SCRIPT_DIR/test.sh" \
    geonode.zalf \
    "$@"
