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
import enum


class Role:
    def __init__(self, label, role_value, is_required, is_multivalue, is_toggled_in_metadata_editor):
        self.label = label
        self.role_value = role_value
        self.is_required = is_required
        self.is_multivalue = is_multivalue
        self.is_toggled_in_metadata_editor = is_toggled_in_metadata_editor

    def __repr__(self):
        return self.label


class Roles(enum.Enum):
    """Roles with their `label`, `role_value` like in people.enumarations, `is_required`, `is_multivalue`, `is_toggled_in_metadata_editor"""

    OWNER = Role("Owner", "owner", True, False, False)
    METADATA_AUTHOR = Role("Author", "author", True, True, True)
    PROCESSOR = Role("Processor", "processor", False, True, True)
    PUBLISHER = Role("Publisher", "publisher", False, True, True)
    CUSTODIAN = Role("Custodian", "custodian", False, True, True)
    POC = Role("Point of Contact", "pointOfContact", True, True, False)
    DISTRIBUTOR = Role("Distributor", "distributor", False, True, True)
    RESOURCE_USER = Role("Resource User", "resourceUser", False, True, True)
    RESOURCE_PROVIDER = Role("Resource Provider", "resourceProvider", False, True, True)
    ORIGINATOR = Role("Originator", "originator", False, True, True)
    PRINCIPAL_INVESTIGATOR = Role("Principal Investigator", "principalInvestigator", False, True, True)
    DATA_COLLECTOR = Role("Data Collector", "dataCollector", False, True, True)
    DATA_CURATOR = Role("Data Curator", "dataCurator", False, True, True)
    EDITOR = Role("Editor", "editor", False, True, True)
    HOSTING_INSTITUTION = Role("Hosting Institution", "hostingInstitution", False, True, True)
    OTHER = Role("Other", "other", False, True, True)
    PRODUCER = Role("Producer", "producer", False, True, True)
    PROJECT_LEADER = Role("Project Leader", "projectLeader", False, True, True)
    PROJECT_MANAGER = Role("Project Manager", "projectManager", False, True, True)
    PROJECT_MEMBER = Role("Project Member", "projectMember", False, True, True)
    REGISTRATION_AGENCY = Role("Registration Agency", "registrationAgency", False, True, True)
    REGISTRATION_AUTHORITY = Role("Registration Authority", "registrationAuthority", False, True, True)
    RELATED_PERSON = Role("Related Person", "relatedPerson", False, True, True)
    RESEARCH_GROUP = Role("Research Group", "researchGroup", False, True, True)
    RESEARCHER = Role("Researcher", "researcher", False, True, True)
    RIGHTS_HOLDER = Role("Rights Holder", "rightsHolder", False, True, True)
    SPONSOR = Role("Sponsor", "sponsor", False, True, True)
    SUPERVISOR = Role("Supervisor", "supervisor", False, True, True)
    WORK_PACKAGE_LEADER = Role("Work Package Leader", "workPackageLeader", False, True, True)
    
    @property
    def name(self):
        return super().name.lower()

    @property
    def label(self):
        return self.value.label

    @property
    def role_value(self):
        return self.value.role_value

    @property
    def is_required(self):
        return self.value.is_required

    @property
    def is_multivalue(self):
        return self.value.is_multivalue

    @property
    def is_toggled_in_metadata_editor(self):
        return self.value.is_toggled_in_metadata_editor

    def __repr__(self):
        return self.name

    @classmethod
    def get_required_ones(cls):
        return [role for role in cls if role.is_required]

    @classmethod
    def get_multivalue_ones(cls):
        return [role for role in cls if role.is_multivalue]

    @classmethod
    def get_toggled_ones(cls):
        return [role for role in cls if role.is_toggled_in_metadata_editor]
