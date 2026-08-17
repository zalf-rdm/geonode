#!/bin/bash
set -e

# Resolve the repository root so this script behaves the same however it is invoked:
# `./tests/test.sh ...` from the repo root (how CI calls it) or `./test.sh ...` from tests/.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
. "$ROOT_DIR/.env_test"
set +a

# NOTE: `paver setup_data` used to run here. pavement.py was removed upstream and paver is not a
# dependency, so that line aborted every suite before a single test ran. It only imported gisdata
# sample layers into the *dev* database via `manage.py importlayers`; unit tests use Django's own
# test_* databases and do not need it.

coverage run --branch --source=geonode manage.py test -v 3 --keepdb "$@"
