import logging
import itertools
import datetime

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied, BadRequest, ValidationError
from django.contrib.auth.decorators import login_required

from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from oauth2_provider.contrib.rest_framework import OAuth2Authentication

from geonode.base.models import ResourceBase
from geonode.maps.models import Map, MapLayer
from geonode.zalf.api.serializer import PublishSerializer

logger = logging.getLogger(__name__)

allowed_authentication_classes = [
    BasicAuthentication,
    SessionAuthentication,
    OAuth2Authentication,
]

def _approve_data_collection(user, map_resource: Map):

    def approve_resource(resource):
        resource.is_approved = True
        # first save to ensure permission update loads status from db
        resource.save()
        resource.set_permissions(approval_status_changed=True)
        # now save the permission change
        resource.save()
    
    # status.approved_at = datetime.utcnow()
    to_approve = [ 
        map_resource,
        *set(
            filter(
                # linked and owned resource
                lambda resource: resource.owner == user, 
                [ lr.target for lr in map_resource.get_linked_resources() ]
            ),
        )
    ]

    [ approve_resource(resource) for resource in to_approve ]
    
    return JsonResponse({
        "success": True,
        "message": "Data Collection approved"
    })


@api_view(['POST'])
@authentication_classes(allowed_authentication_classes)
def approve_data_collection_post(request, mapid):
    user = request.user
    map = get_object_or_404(Map, id=mapid, owner=user)
    if not user.can_approve(map):
        raise PermissionDenied(_("Permission Denied"))
    
    return _approve_data_collection(user, map_resource=map)


# @api_view(['GET'])
# def approve_data_collection_get(request):
#     if not "uuid" in request.GET:
#         raise BadRequest("The 'uuid' parameter is required")
#     uuid = request.GET["uuid"]
#     try:
#         status = Map.objects.get(approval_code=uuid)
#     except (ValidationError, Map.DoesNotExist):
#         logger.debug(f"Ignore (invalid) approval code: '{uuid}'")
#         raise BadRequest("Invalid approval code!")

#     return _approve_data_collection(status=status)



def _publish_data_collection(user, map: Map, payload):

    def publish_resource(resource):
        resource.is_published = True
        # first save to ensure permission update loads status from db
        resource.save()
        resource.set_permissions(approval_status_changed=True)
        # now save the permission change
        resource.save()
    
    # linked resources contains map layers
    linked_resources = set(
        filter(
            lambda resource: (
                resource.id in payload.linked_resources
                and 
                resource.owner == user
                and
                not resource.is_published
            ),
            [ lr.target for lr in map.get_linked_resources() ]
        )
    )

    to_publish = [ map, *linked_resources ]
    
    doi_prefix = payload.doi_prefix
    if doi_prefix:

        # TODO check if doi_prefix is valid
        # TODO check if doi_prefix matches group

        # TODO register DOI

        pass


    [ publish_resource(resource) for resource in to_publish ]
    
    return JsonResponse({
        "success": True,
        "message": "Data Collection published"
    })



@api_view(['POST'])
@authentication_classes(allowed_authentication_classes)
def publish_data_collection(request, mapid):

    user = request.user
    map = get_object_or_404(Map, id=mapid, owner=user)
    if not user.can_publish(map):
        raise PermissionDenied(_("Permission Denied"))

    serializer = PublishSerializer(request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    return _publish_data_collection(user, map, payload)