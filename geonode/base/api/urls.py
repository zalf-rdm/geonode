#########################################################################
#
# Copyright (C) 2020 OSGeo
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
from geonode.api.urls import router

from . import views

router.register(r"groups", views.GroupViewSet, "group-profiles")
router.register(r"resources", views.ResourceBaseViewSet, "base-resources")
router.register(r"owners", views.OwnerViewSet, "owners")
router.register(r"categories", views.TopicCategoryViewSet, "categories")
router.register(r"licenses", views.LicenseViewSet, "licenses")
router.register(r"relationtypes", views.RelationTypeViewSet, "relationtypes")
router.register(r"relatedidentifiertypes", views.RelatedIdentifierTypeViewSet, "relatedidentifiertypes")
router.register(r"relatedidentifiers", views.RelatedIdentifierViewSet, "relatedidentifiers")
router.register(r"organizations", views.OrganizationViewSet, "organizations")
router.register(r"fundings", views.FundingViewSet, "fundings")
router.register(r"relatedprojects", views.RelatedProjectViewSet, "relatedprojects")
router.register(r"keywords", views.HierarchicalKeywordViewSet, "keywords")
router.register(r"tkeywords", views.ThesaurusKeywordViewSet, "tkeywords")
router.register(r"tkeywordlabels", views.ThesaurusKeywordLabelViewSet, "tkeywordlabels")
router.register(r"regions", views.RegionViewSet, "regions")

urlpatterns = []
