#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# NOTE: this script used to end in `paver run_tests` (removed upstream, see tests/test.sh).
# Runs the upload app's unit tests. The GeoServer-backed end2end/integration modules stay off by
# default; enable them with TEST_RUN_INTEGRATION_UPLOAD=True via tests/test_integration.sh.

"$SCRIPT_DIR/test.sh" \
    geonode.upload \
    "$@"
