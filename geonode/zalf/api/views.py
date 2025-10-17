import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied, BadRequest, ValidationError

from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from oauth2_provider.contrib.rest_framework import OAuth2Authentication

from geonode.maps.models import Map
from geonode.zalf.api.serializer import PublishSerializer

logger = logging.getLogger(__name__)

allowed_authentication_classes = [
    BasicAuthentication,
    SessionAuthentication,
    OAuth2Authentication,
]

def _update_resource_status(resource, is_approved=None, is_published=None):
    if is_approved != None:
        resource.is_approved = is_approved
    if is_published != None:
        resource.is_published

    # first save to ensure permission update loads status from db
    resource.save()
    resource.set_permissions(approval_status_changed=True)
    # now save the permission change
    resource.save()

def _approve_data_collection(user, map_resource: Map):

    to_approve = [ 
        map_resource,
        *set(
            filter(
                lambda resource: resource.owner == user, 
                # map layers are also just linked resources
                [ lr.target for lr in map_resource.get_linked_resources() ]
            ),
        )
    ]
    
    [ _update_resource_status(resource, is_approved=True) for resource in to_approve ]
    
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

    resources = set(
        filter(
            lambda resource: (
                resource.id in payload.resources
                and
                not resource.is_published
                and 
                resource.owner == user
            ),
            # map layers are also just linked resources
            [ lr.target for lr in map.get_linked_resources() ]
        )
    )

    for resource in resources:
        if not resource.is_approved:
            raise ValidationError(_(f"Resource '{resource.title}' (ID: {resource.id}) is not approved, yet!"))


    to_publish = [ map, *resources ]
    
    doi_prefix = payload.doi_prefix
    if doi_prefix:

        # TODO check if doi_prefix is valid
        # TODO check if doi_prefix matches group

        # TODO register DOI

        pass

    [ _update_resource_status(resource, is_published=True) for resource in to_publish ]
    
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