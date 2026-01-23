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
from django.utils.translation import gettext_lazy as _

ROLE_VALUES = (
    ("author", _("party who authored the resource")),
    ("processor", _("party who has processed the data in a manner such that the resource has been modified")),
    ("publisher", _("party who published the resource")),
    (
        "custodian",
        _(
            "party that accepts accountability and responsibility for the data and ensures \
        appropriate care and maintenance of the resource"
        ),
    ),
    ("pointOfContact", _("party who can be contacted for acquiring knowledge about or acquisition of the resource")),
    ("distributor", _("party who distributes the resource")),
    ("user", _("party who uses the resource")),
    ("resourceProvider", _("party that supplies the resource")),
    ("originator", _("party who created the resource")),
    ("owner", _("party that owns the resource")),
    ("principalInvestigator", _("key party responsible for gathering information and conducting research")),
    (
        "dataCollector",
        _(
            "Person/institution responsible for finding, gathering/collecting data under the guidelines of the au-thor(s) or Principal Investigator (PI)."
        ),
    ),
    (
        "dataCurator",
        _(
            "Person tasked with reviewing, enhancing, cleaning, or standardiz-ing metadata and the associated data submitted for storage, use, and maintenance within a data centre or repository."
        ),
    ),
    ("editor", _("A person who oversees the details related to the publication format of the resource.")),
    (
        "hostingInstitution",
        _(
            "Typically, the organisation allowing the resource to be available on the internet through the provision of its hardware/software/operating support."
        ),
    ),
    (
        "other",
        _(
            "Any person or institution making a significant contribution to the development and/or maintenance of the resource, \
            but whose contribution does not “fit” other con-trolled vocabulary for Type."
        ),
    ),
    ("producer", _("Typically a person or organisation responsible for the artistry and form of a media product.")),
    (
        "projectLeader",
        _(
            "Person officially designated as head of project team or subproject team instrumental in the work necessary to development of the resource."
        ),
    ),
    (
        "projectManager",
        _(
            "Person officially designated as manager of a project. Project may consist of one or many project teams and sub-teams."
        ),
    ),
    ("projectMember", _("Person on the membership list of a designated project/project team.")),
    (
        "registrationAgency",
        _(
            "Institution/organisation officially appointed by a Registration Authority to handle specific tasks within a defined area of responsibility."
        ),
    ),
    (
        "registrationAuthority",
        _("A standards-setting body from which Registration Agencies obtain official recognition and guidance."),
    ),
    (
        "relatedPerson",
        _(
            "A person without a specifically defined role in the development of the resource, but who is someone the author wishes to recognize."
        ),
    ),
    (
        "researchGroup",
        _(
            "Typically refers to a group of indi-viduals with a lab, department, or division; the group has a particular, defined focus of activity."
        ),
    ),
    (
        "researcher",
        _(
            "A person involved in analysing data or the results of an experiment or formal study. May indicate an intern or assistant \
            to one of the authors who helped with research but who was not so “key” as to be listed as an author."
        ),
    ),
    (
        "rightsHolder",
        _(
            "Person or institution owning or managing property rights, including intellectual property rights over the resource."
        ),
    ),
    (
        "sponsor",
        _(
            "Person or organisation that issued a contract or under the auspices of which a work has been written, printed, published, developed, etc."
        ),
    ),
    (
        "supervisor",
        _(
            "Designated administrator over one or more groups/teams working to produce a resource or over one or more steps of a development pro-cess."
        ),
    ),
    (
        "workPackageLeader",
        _(
            "A Work Package is a recognized data product, not all of which is included in publication. The pack-age, \
            instead, may include notes, discarded documents, etc. The Work Package Leader is responsi-ble for ensuring the comprehen-sive contents, \
            versioning, and availability of the Work Package during the development of the resource."
        ),
    ),
)
