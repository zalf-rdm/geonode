#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

coverage run --branch --source=geonode manage.py test \
  geonode.api.tests.UserAndTokenInfoApiTests \
  geonode.people.socialaccount.providers.geonode_openid_connect.tests \
  -v 3 --keepdb --noinput
