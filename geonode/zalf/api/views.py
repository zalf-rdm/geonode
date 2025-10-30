import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, BadRequest, ValidationError

from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from oauth2_provider.contrib.rest_framework import OAuth2Authentication

from geonode.utils import http_client
from geonode.maps.models import Map
from geonode.zalf.api.serializer import PublishSerializer

logger = logging.getLogger(__name__)

allowed_authentication_classes = [
    SessionAuthentication,
    BasicAuthentication,
    OAuth2Authentication,
]

def _get_owner(id):
    user_model = get_user_model()
    try:
        return user_model.objects.get(id=id)
    except user_model.DoesNotExist:
        raise BadRequest("User does not exist")

def _update_resource_status(resource, is_approved=None, is_published=None):
    if is_approved != None:
        resource.is_approved = is_approved
    if is_published != None:
        resource.is_published = is_published

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
    owner = request.data["owner"]
    user = _get_owner(id=owner)
    map = get_object_or_404(Map, id=mapid)
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



def _publish_data_collection(map: Map, payload):

    owner = _get_owner(id=payload["owner"])
    resources = set(
        filter(
            lambda resource: (
                resource.id in payload["resources"]
                and
                not resource.is_published
                and 
                resource.owner == owner
            ),
            # map layers are also just linked resources
            [ lr.target for lr in map.get_linked_resources() ]
        )
    )

    for resource in resources:
        if not resource.is_approved:
            raise ValidationError(_(f"Resource '{resource.title}' (ID: {resource.id}) is not approved, yet!"))


    to_publish = [ map, *resources ]
    
    doi_prefix = getattr(payload, "doi_prefix", False)
    if doi_prefix:

        # TODO check if doi_prefix is valid
        # TODO check if doi_prefix matches group

        # TODO register DOI

        # Prepare the metadata
        

        doi_url = settings.ZALF_DATACITE_BASE_URL
        doi_agent = settings.ZALF_DATACITE_AGENT
        doi_username = settings.ZALF_DATACITE_USERNAME
        doi_password = settings.ZALF_DATACITE_PASSWORD

        headers = {
            "Content-Type": "application/vnd.api+json"
        }

        # TODO we can use
        # http_client.post(...)

        pass

    [ _update_resource_status(resource, is_published=True) for resource in to_publish ]
    
    return JsonResponse({
        "success": True,
        "message": "Data Collection published"
    })



@api_view(['POST'])
@authentication_classes(allowed_authentication_classes)
def publish_data_collection(request, mapid):

    map = get_object_or_404(Map, id=mapid)
    user = request.user
    if not user.can_publish(map):
        # TODO fine granular permissions necessary? (which only allow data stewards to publish)
        raise PermissionDenied(_("Permission Denied"))

    serializer = PublishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    return _publish_data_collection(map, payload)