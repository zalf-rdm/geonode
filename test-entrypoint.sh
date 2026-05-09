#!/bin/bash
# Install missing dependencies that are in requirements.txt but not in the Docker image
echo "Installing missing dependencies..."
pip install -q zipstream-ng || true
pip install -q -e git+https://github.com/GeoNodeUserGroup-DE/contrib_datapackage.git@geonode-v4.4.3+datapackage002#egg=importer_datapackage || true

# Run the original entrypoint
exec /usr/src/geonode/entrypoint.sh "$@"
