#!/usr/bin/env python
#########################################################################
#
# Copyright (C) 2026 ZALF
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
"""Print the space-separated test module list for a named CI suite.

Used by .github/workflows/tests.yml so the suite definitions do not have to be
embedded as nested `python -c '...'` one-liners inside YAML inside a shell
heredoc, where the quoting is easy to get silently wrong.

Usage:  python tests/suite_apps.py {main|security|gis_backend}
"""
import sys

from geonode import settings

GROUPS = {
    # everything except the suites that get their own job below
    "main": lambda a: not any(k in a for k in ("security", "geoserver", "upload")),
    "security": lambda a: "security" in a,
    "gis_backend": lambda a: "geoserver" in a,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in GROUPS:
        sys.stderr.write(f"usage: {argv[0]} {{{'|'.join(GROUPS)}}}\n")
        return 2
    predicate = GROUPS[argv[1]]
    print(" ".join(f"{app}.tests" for app in settings.GEONODE_APPS if predicate(app)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
