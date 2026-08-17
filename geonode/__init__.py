#########################################################################
#
# Copyright (C) 2016 OSGeo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

import os

__version__ = (5, 0, 3, "post", 1)
# Static version string consumed by pyproject.toml's dynamic version
# (`[tool.setuptools.dynamic] version = {attr = "geonode.__version_str__"}`).
# setuptools reads this attribute statically at build time, so it must be a
# plain string literal and kept in sync with __version__.
__version_str__ = "5.0.3"


def get_version():
    import geonode.version

    return geonode.version.get_version(__version__)


def main(_, **settings):
    from django.core.wsgi import get_wsgi_application

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings.get("django_settings"))
    app = get_wsgi_application()
    return app


class GeoNodeException(Exception):
    """Base class for exceptions in this module."""

    pass
