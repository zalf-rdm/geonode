import logging
import datetime

from django.http import JsonResponse
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, BadRequest, ValidationError

from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from oauth2_provider.contrib.rest_framework import OAuth2Authentication

from geonode.maps.models import Map
from geonode.zalf.api.serializer import PublishSerializer
from geonode.zalf.api.datacite import (
    validate_doi_prefix,
    register_doi,
    get_datacite_account_for_prefix,
)

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
        raise Http404("User does not exist")


def _update_resource_status(resource, is_approved=None, is_published=None):
    if is_approved is not None:
        resource.is_approved = is_approved
    if is_published is not None:
        resource.is_published = is_published
        if is_published:
            today = datetime.date.today()
            now = datetime.datetime.now()
            if not resource.date_available:
                resource.date_available = today
            if not resource.date_issued:
                resource.date_issued = today
            if not resource.date:
                resource.date = now

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
                [lr.target for lr in map_resource.get_linked_resources()],
            ),
        ),
    ]

    for resource in to_approve:
        _update_resource_status(resource, is_approved=True)

    return JsonResponse({"success": True, "message": "Data Collection approved"})


@api_view(["POST"])
@authentication_classes(allowed_authentication_classes)
def approve_data_collection_post(request, mapid):
    # Authorization: always check the *authenticated* user, never the payload.
    # We use can_publish_data_collection() (group membership in ZALF_DATACITE_ACCOUNTS groups)
    # rather than GeoNode's can_approve() which requires the resource to be assigned to the
    # user's group as a manager — a setup constraint that doesn't apply to our workflow.
    if not request.user.is_authenticated:
        raise PermissionDenied(_("Authentication required"))
    if not request.user.can_publish_data_collection():
        raise PermissionDenied(_("Permission Denied"))
    map = get_object_or_404(Map, id=mapid)

    # The owner field is used only to filter which linked resources to approve.
    owner_id = request.data.get("owner")
    if not owner_id:
        raise BadRequest("Owner ID is required")
    owner = _get_owner(id=owner_id)

    return _approve_data_collection(owner, map_resource=map)


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


def _publish_data_collection(map: Map, payload, user):
    """
    Publish a data collection (map + linked resources).

    The *user* parameter is the **authenticated request user** — used to
    resolve which DataCite account/credentials to use for the requested prefix.
    """
    owner = _get_owner(id=payload["owner"])
    resources = set(
        filter(
            lambda resource: (
                resource.id in payload["resources"] and not resource.is_published and resource.owner == owner
            ),
            # map layers are also just linked resources
            [lr.target for lr in map.get_linked_resources()],
        )
    )

    for resource in resources:
        if not resource.is_approved:
            raise ValidationError(_(f"Resource '{resource.title}' (ID: {resource.id}) is not approved, yet!"))

    to_publish = [map, *resources]

    doi_prefix = payload.get("doi_prefix")
    collection_doi = None

    if doi_prefix:
        # Validate the DOI prefix format
        validate_doi_prefix(doi_prefix)

        # Ensure the authenticated user is allowed to use this prefix.
        # get_datacite_account_for_prefix raises ValidationError if not.
        get_datacite_account_for_prefix(doi_prefix, user=user)

        # Register a single DOI for the whole collection, using the map's UUID as suffix.
        # All resources in the collection will share this one DOI.
        try:
            collection_doi = register_doi(map, doi_prefix, doi_suffix=str(map.uuid), user=user)
            logger.info(f"Registered collection DOI '{collection_doi}' for map '{map.title}' (ID: {map.id})")
        except ValidationError as e:
            logger.error(f"DOI registration failed for data collection map '{map.title}': {e}")
            raise ValidationError(
                _(f"DOI registration failed for data collection '{map.title}' (ID: {map.id}): {e.message}")
            )

        # Assign the same DOI to every resource in the collection
        # collection_doi is already an FQDN (https://doi.org/...) as returned by register_doi
        for resource in resources:
            resource.doi = collection_doi
            resource.save(update_fields=["doi"])
            logger.info(
                f"Assigned collection DOI '{collection_doi}' to resource '{resource.title}' (ID: {resource.id})"
            )
    else:
        raise ValidationError(_("DOI prefix is required"))

    [_update_resource_status(resource, is_published=True) for resource in to_publish]

    response_data = {
        "success": True,
        "message": "Data Collection published",
    }

    if collection_doi:
        response_data["doi"] = collection_doi

    return JsonResponse(response_data)


@api_view(["POST"])
@authentication_classes(allowed_authentication_classes)
def publish_data_collection(request, mapid):

    if not request.user.is_authenticated:
        raise PermissionDenied(_("Authentication required"))

    map = get_object_or_404(Map, id=mapid)
    user = request.user

    if not user.can_publish_data_collection():
        raise PermissionDenied(_("Permission Denied"))

    serializer = PublishSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data

    return _publish_data_collection(map, payload, user=user)
