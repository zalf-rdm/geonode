# Set variables to pass
DOCKER_HOST := $(DOCKER_HOST)
DOCKER_HOST_IP := `docker run --net=host codenvy/che-ip:nightly`

auto-up:
	# bring up the services with proper environment variables
	unset DOCKERHOST; \
	export DOCKERHOST=$(DOCKER_HOST); \
	echo Docker daemon is running at the following address $$DOCKERHOST; \
	unset GEONODE_LB_HOST_IP; \
	export GEONODE_LB_HOST_IP=$(DOCKER_HOST_IP); \
	echo GeoNode will be available at the following address http://$$GEONODE_LB_HOST_IP; \
	echo If you want to run it on localhost then remember to add this line "localhost $$GEONODE_LB_HOST_IP" to /etc/hosts; \
	docker-compose up -d --build

up:
	docker-compose up -d

build:
	docker-compose build django
	docker-compose build celery

sync: up
	# set up the database tables
	docker-compose exec django django-admin.py migrate --noinput
	docker-compose exec django django-admin.py loaddata sample_admin
	docker-compose exec django django-admin.py loaddata geonode/base/fixtures/default_oauth_apps_docker.json
	docker-compose exec django django-admin.py loaddata geonode/base/fixtures/initial_data.json

migrate:
	django-admin.py migrate --noinput

migrate_setup: migrate
	django-admin.py loaddata sample_admin

wait:
	sleep 5

logs:
	docker-compose logs --follow

down:
	docker-compose down

pull:
	docker-compose pull

smoketest: up
	docker-compose exec django python manage.py test geonode.tests.smoke --noinput --nocapture --detailed-errors --verbosity=1 --failfast

unittest: up
	docker-compose exec django python manage.py test geonode.people.tests geonode.base.tests geonode.layers.tests geonode.maps.tests geonode.proxy.tests geonode.security.tests geonode.social.tests geonode.catalogue.tests geonode.documents.tests geonode.api.tests geonode.groups.tests geonode.services.tests geonode.geoserver.tests geonode.upload.tests geonode.tasks.tests --noinput --failfast

test: smoketest unittest

reset: down up wait sync

hardreset: pull build reset

develop: pull build up sync

# Security auditing. Scope: the image this branch builds. Mirrors
# .github/workflows/security-audit.yml so a finding can be reproduced locally.
# This line publishes no `latest` tag, so AUDIT_IMAGE names the newest published image; override it
# to audit another tag, or use audit-build for the working tree.
AUDIT_IMAGE ?= zalf/geonode:v4.4.3-zalf002.59
# This image mixes pip's dist-packages with Ubuntu's, and a system package versioned
# `2.22.1ubuntu1` is not PEP 440, which makes pip-audit fail to enumerate anything. Scoping it to
# pip's directory avoids that.
AUDIT_SITE_PACKAGES ?= /usr/local/lib/python3.10/dist-packages

audit:
	docker run --rm --entrypoint bash $(AUDIT_IMAGE) -c \
		'pip install -q --no-cache-dir pip-audit && pip-audit --path $(AUDIT_SITE_PACKAGES) --progress-spinner=off -f json' \
		> /tmp/pip-audit.json || true
	@python3 -c "import json; json.load(open('/tmp/pip-audit.json'))"
	python3 security/pip_audit_gate.py /tmp/pip-audit.json

audit-baseline:
	# Run after a dependency upgrade, then commit security/pip-audit-known.txt with the upgrade.
	docker run --rm --entrypoint bash $(AUDIT_IMAGE) -c \
		'pip install -q --no-cache-dir pip-audit && pip-audit --path $(AUDIT_SITE_PACKAGES) --progress-spinner=off -f json' \
		> /tmp/pip-audit.json || true
	@python3 -c "import json; json.load(open('/tmp/pip-audit.json'))"
	python3 security/pip_audit_gate.py /tmp/pip-audit.json --write-baseline

audit-image:
	# OS packages (apt) -- the layer pip-audit cannot see.
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image \
		--scanners vuln --severity HIGH,CRITICAL --ignore-unfixed $(AUDIT_IMAGE)

audit-bundled:
	# C libraries vendored inside wheels -- the gap between the two scanners above.
	docker run --rm --entrypoint python -v $(PWD)/security/scan_bundled_libs.py:/scan.py:ro \
		$(AUDIT_IMAGE) -I /scan.py

audit-build:
	docker build --build-arg APT_CACHE_BUST=$$(date +%s) -t geonode-audit:local .
	$(MAKE) audit AUDIT_IMAGE=geonode-audit:local
	$(MAKE) audit-image AUDIT_IMAGE=geonode-audit:local

base-digest:
	# Compare the digest pinned in the Dockerfile against what the base image tag resolves to now.
	@docker buildx imagetools inspect $$(grep -oP '(?<=^FROM )[^@ ]+' Dockerfile) \
		--format 'Live digest:   {{.Manifest.Digest}}'
	@grep -oP '(?<=@)sha256:\S+' Dockerfile | sed 's/^/Pinned digest: /'

