# Digest-pinned, so builds are reproducible and an OS-layer change cannot arrive silently on
# whichever day upstream republishes the tag. Check by hand with `make base-digest`.
FROM geonode/geonode-base:latest-ubuntu-22.04@sha256:0728153a2a39471d5979e75f2904474e1d9380e04e1ce2db65934314bdbe4d9c
LABEL GeoNode development team

# GeoNode republishes the base on its own cadence, so an Ubuntu security update can sit unapplied in
# it for weeks. Upgrading explicitly is what makes a rebuild deliver distro patches while the base
# stays digest-pinned; without it, rebuilding a pinned base just reproduces the same packages.
# Placed directly after FROM so everything below still caches normally.
#
# The cache bust matters as much as the upgrade: a build whose Dockerfile has not changed would
# restore this layer from cache and install nothing. CI passes a unique value per build.
ARG APT_CACHE_BUST=local
RUN echo "Refreshing OS packages (${APT_CACHE_BUST})" \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get autoremove --purge -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# copy local geonode src inside container
COPY . /usr/src/geonode/
WORKDIR /usr/src/geonode

#COPY monitoring-cron /etc/cron.d/monitoring-cron
#RUN chmod 0644 /etc/cron.d/monitoring-cron
#RUN crontab /etc/cron.d/monitoring-cron
#RUN touch /var/log/cron.log
#RUN service cron start

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
# RUN cd /usr/src/geonode-contribs/ldap; pip install --upgrade  -e .

RUN yes w | pip install --src /usr/src -r requirements.txt &&\
    yes w | pip install -e .

# Export ports
EXPOSE 8000

# We provide no command or entrypoint as this image can be used to serve the django project or run celery tasks
# ENTRYPOINT /usr/src/geonode/entrypoint.sh
