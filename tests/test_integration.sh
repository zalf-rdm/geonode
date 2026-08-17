#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# NOTE: this script used to end in `paver run_tests` and call scripts/misc/create_dbs_travis.sh.
# Both were removed upstream (pavement.py deleted; the travis helper no longer exists), so it
# could not run at all. Database creation is handled by the test stack / Django's test runner.
#
# These suites need a live GeoServer and are NOT part of the PR gate -- run them deliberately.

export TEST_RUN_INTEGRATION=True
export TEST_RUN_INTEGRATION_SERVER=${TEST_RUN_INTEGRATION_SERVER:-True}
export TEST_RUN_INTEGRATION_UPLOAD=${TEST_RUN_INTEGRATION_UPLOAD:-False}
export TEST_RUN_INTEGRATION_CSW=${TEST_RUN_INTEGRATION_CSW:-False}
export TEST_RUN_INTEGRATION_MONITORING=${TEST_RUN_INTEGRATION_MONITORING:-False}
export TEST_RUN_INTEGRATION_BDD=${TEST_RUN_INTEGRATION_BDD:-False}

if [ "$#" -gt 0 ]; then
    "$SCRIPT_DIR/test.sh" "$@"
else
    "$SCRIPT_DIR/test.sh" \
        geonode.geoserver.tests.integration \
        geonode.upload.tests.integration \
        geonode.thumbs.tests.test_integration \
        geonode.harvesting.tests.test_integrations
fi
