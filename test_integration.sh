#!/bin/bash

echo "DEBUG: SCRIPT UPDATED"

export BACKEND=geonode.geoserver
export DOCKER_COMPOSE_VERSION=1.19.0
export GEOSERVER_SERVER_URL=http://localhost:8080/geoserver/
export GEOSERVER_SERVER_PORT=8080
export ON_TRAVIS=True
export TEST_RUNNER_KEEPDB=True
export TEST_RUN_INTEGRATION=True
export TEST_RUN_INTEGRATION_SERVER=True
export TEST_RUN_INTEGRATION_UPLOAD=False
export TEST_RUN_INTEGRATION_MONITORING=False
export TEST_RUN_INTEGRATION_CSW=False
export TEST_RUN_INTEGRATION_BDD=False
export MONITORING_ENABLED=False
export USER_ANALYTICS_ENABLED=False
export SESSION_EXPIRED_CONTROL_ENABLED=True
export CELERY_ALWAYS_EAGER=True

# coverage run --branch --source=geonode manage.py test --noinput --parallel=1 $@
echo "Initialize DB";
# Inline DB setup for Docker
echo "Setting up PostGIS Backend for Docker"
export PGPASSWORD=${POSTGRES_PASSWORD:-postgres}
DB_HOST=${DATABASE_HOST:-db}
DB_USER=${POSTGRES_USER:-postgres}

# Drop databases
psql -h $DB_HOST -U $DB_USER -c "DROP DATABASE IF EXISTS template_postgis;"
psql -h $DB_HOST -U $DB_USER -c "DROP DATABASE IF EXISTS geonode;"
psql -h $DB_HOST -U $DB_USER -c "DROP DATABASE IF EXISTS geonode_data;"
psql -h $DB_HOST -U $DB_USER -c "DROP DATABASE IF EXISTS upload_test;"
psql -h $DB_HOST -U $DB_USER -c "DROP DATABASE IF EXISTS test_upload_test;"

# Create template_postgis
psql -h $DB_HOST -U $DB_USER -c "CREATE DATABASE template_postgis;"
psql -h $DB_HOST -U $DB_USER -d template_postgis -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -h $DB_HOST -U $DB_USER -d template_postgis -c "GRANT ALL ON geometry_columns TO PUBLIC;"
psql -h $DB_HOST -U $DB_USER -d template_postgis -c "GRANT ALL ON spatial_ref_sys TO PUBLIC;"

# Create databases from template
psql -h $DB_HOST -U $DB_USER -c "CREATE DATABASE geonode TEMPLATE template_postgis OWNER geonode;"
psql -h $DB_HOST -U $DB_USER -c "CREATE DATABASE geonode_data TEMPLATE template_postgis OWNER geonode;"
psql -h $DB_HOST -U $DB_USER -c "CREATE DATABASE upload_test TEMPLATE template_postgis OWNER geonode;"


paver run_tests --coverage --local false