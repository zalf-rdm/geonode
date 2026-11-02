
# Deliberately not digest-pinned: the OS layer must never be held back. Every build re-resolves
# this tag, so it starts from whatever upstream published most recently, and the `apt-get upgrade`
# below then installs everything Ubuntu has released since -- nothing pinned, held or excluded
# anywhere in between.
#
# The tradeoff is accepted knowingly: two builds of the same commit can start from different bases,
# so an image is reproducible only to the day it was built, and an OS-layer change can arrive on
# whichever day upstream republishes the tag. Getting security updates in unimpeded is worth more
# here than byte-identical rebuilds. `make base-digest` shows what the tag resolves to right now,
# and .github/workflows/base-image-refresh.yml records it weekly so the rollout is still traceable.
FROM geonode/geonode-base:latest-ubuntu-24.04
LABEL GeoNode development team

# GeoNode republishes the base on its own cadence, so an Ubuntu security update can sit unapplied in
# it for weeks -- CVE-2026-111497 found libbrotli1 1.1.0-2build2 here, with no distro fix released
# yet. Following the tag is not enough on its own: upstream's republish cadence decides how fresh
# the base is, and upgrading explicitly is what closes the gap between that and what Ubuntu has
# actually released. Placed directly after FROM so everything below still caches normally.
#
# The cache bust matters as much as the upgrade: a build whose Dockerfile has not changed would
# restore this layer from cache and install nothing. CI passes a unique value per build, exactly as
# it does for the Python layer below, so every published image re-resolves apt.
ARG APT_CACHE_BUST=local
RUN echo "Refreshing OS packages (${APT_CACHE_BUST})" \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get autoremove --purge -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/src/geonode
# copy local geonode src inside container
COPY . /usr/src/geonode/
WORKDIR /usr/src/geonode

COPY wait-for-databases.sh /usr/bin/wait-for-databases
RUN chmod +x /usr/bin/wait-for-databases
RUN chmod +x /usr/src/geonode/tasks.py \
    && chmod +x /usr/src/geonode/entrypoint.sh

COPY celery.sh /usr/bin/celery-commands
RUN chmod +x /usr/bin/celery-commands

COPY celery-cmd /usr/bin/celery-cmd
RUN chmod +x /usr/bin/celery-cmd

# # Install "geonode-contribs" apps
# RUN cd /usr/src; git clone https://github.com/GeoNode/geonode-contribs.git -b master
# # Install logstash and centralized dashboard dependencies
# RUN cd /usr/src/geonode-contribs/geonode-logstash; pip install --upgrade  -e . \
#     cd /usr/src/geonode-contribs/ldap; pip install --upgrade  -e .

# The project intentionally allows the latest compatible ZALF MapStore client.
# CI supplies a unique value for each image build so a manual workflow rerun
# resolves newly published Python packages instead of restoring this layer.
ARG PYTHON_DEPENDENCY_CACHE_BUST=local
RUN echo "Refreshing Python dependencies (${PYTHON_DEPENDENCY_CACHE_BUST})" \
    && yes w | pip install --no-cache-dir -e . \
    && python -c "from importlib.metadata import version; print('Installed MapStore client:', version('zalf-django-geonode-mapstore-client'))"

# Export ports
EXPOSE 8000

# We provide no command or entrypoint as this image can be used to serve the django project or run celery tasks
# ENTRYPOINT /usr/src/geonode/entrypoint.sh
