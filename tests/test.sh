#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTS_DIR="$ROOT_DIR/tests"

set -a
. "$ROOT_DIR/.env_test"
set +a

cd "$TESTS_DIR"
paver setup_data
coverage run --branch --source=geonode ../manage.py test -v 3 --keepdb $@
