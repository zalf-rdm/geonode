FROM geonode/geonode-base:latest-ubuntu-24.04
LABEL GeoNode development team

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

# Cleanup apt update lists
RUN apt-get autoremove --purge &&\
    apt-get clean &&\
    rm -rf /var/lib/apt/lists/*

# Export ports
EXPOSE 8000

# We provide no command or entrypoint as this image can be used to serve the django project or run celery tasks
# ENTRYPOINT /usr/src/geonode/entrypoint.sh
