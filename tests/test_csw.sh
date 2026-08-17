#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# NOTE: this script used to end in `paver run_tests`. pavement.py no longer exists and paver is
# not a dependency, so it could never run. It now routes through tests/test.sh like every other
# suite. Everything else (DATABASE_URL, GEOSERVER_*, SITEURL, ...) comes from .env_test, which
# test.sh sources -- duplicating those exports here only risked drifting out of sync with it.

"$SCRIPT_DIR/test.sh" \
    geonode.tests.csw \
    geonode.catalogue.backends.tests \
    "$@"
