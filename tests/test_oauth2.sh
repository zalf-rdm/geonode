#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/tests/test.sh" \
  geonode.api.tests.UserAndTokenInfoApiTests \
  geonode.people.socialaccount.providers.geonode_openid_connect.tests
