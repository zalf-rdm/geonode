#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
. ./.env_test
set +a

paver setup_data
coverage run --branch --source=geonode manage.py test -v 3 --keepdb $@
