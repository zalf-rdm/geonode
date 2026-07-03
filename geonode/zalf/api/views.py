import logging
import datetime

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, BadRequest, ValidationError

from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.response import Response
from oauth2_provider.contrib.rest_framework import OAuth2Authentication

from geonode.base.models import ResourceBase
from geonode.maps.models import Map
from geonode.security.registry import permissions_registry
from geonode.maps.utils import compare_metadata, get_syncable_resources, sync_metadata
from geonode.zalf.api.serializer import PublishSerializer
from geonode.zalf.api.datacite import (
    validate_doi_prefix,
    register_doi,
    get_datacite_account_for_prefix,
    get_datacite_xml,
    get_doi_prefixes_for_user,
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


def _build_public_perm_spec(resource):
    """
    Current perm spec merged with public grants for the anonymous and
    registered-members groups: maps get view; all other resource types
    (datasets, documents, ...) get view + download.
    """
    from django.contrib.auth.models import Group
    from geonode.groups.conf import settings as groups_settings

    perms = ["view_resourcebase"]
    if resource.resource_type != "map":
        perms.append("download_resourcebase")

    perm_spec = permissions_registry.get_perms(instance=resource, include_virtual=False)
    groups = perm_spec.setdefault("groups", {})
    # filter() instead of get(): a missing registered-members group degrades to a no-op
    for grp in Group.objects.filter(name__in=["anonymous", groups_settings.REGISTERED_MEMBERS_GROUP_NAME]):
        groups[grp] = sorted(set(groups.get(grp, [])) | set(perms))
    return perm_spec


def _restore_owner_perms(resource, owner_perms):
    """
    Re-assign the owner's pre-existing permissions after a set_permissions()
    call.  GeoNode's advanced-workflow fixup (get_workflow_permissions) strips
    the owner's edit/manage permissions from any perm spec once the resource
    is approved or published — regardless of the approval_status_changed flag —
    so we bypass the workflow and restore them directly via guardian.
    """
    from guardian.shortcuts import assign_perm

    resource_base = resource.get_self_resource()
    current = set(permissions_registry.get_perms(instance=resource_base, user=resource.owner, include_virtual=False))
    for perm in set(owner_perms) - current:
        try:
            if perm in ("change_dataset_data", "change_dataset_style"):
                # dataset-specific perms live on the concrete Dataset object
                assign_perm(perm, resource.owner, resource.get_real_instance())
            else:
                assign_perm(perm, resource.owner, resource_base)
        except Exception as e:
            logger.warning(f"Could not restore owner permission '{perm}' on '{resource.title}': {e}")
    permissions_registry.delete_resource_permissions_cache(instance=resource_base)


def _update_resource_status(resource, is_approved=None, is_published=None):
    updates = {}
    if is_approved is not None:
        updates["is_approved"] = is_approved
        updates["was_approved"] = is_approved
    if is_published is not None:
        updates["is_published"] = is_published
        updates["was_published"] = is_published
        if is_published:
            today = datetime.date.today()
            now = datetime.datetime.now()
            if not resource.date_available:
                updates["date_available"] = today
            if not resource.date_issued:
                updates["date_issued"] = today
            if not resource.date:
                updates["date"] = now

    # Snapshot the owner's perms before any change so they can be restored
    # after the workflow fixup strips them (see _restore_owner_perms).
    owner_perms = permissions_registry.get_perms(
        instance=resource.get_self_resource(), user=resource.owner, include_virtual=False
    )

    # Write status fields directly to avoid triggering ResourceBase.save() which
    # auto-fires set_permissions(approval_status_changed=True) and the related
    # signal machinery.
    ResourceBase.objects.filter(uuid=resource.uuid).update(**updates)
    resource.refresh_from_db()
    if is_published:
        # Grant public visibility explicitly: the workflow fixup only adds
        # anonymous perms when approval_status_changed=True, which we avoid.
        # Since is_published is already True in the DB, the fixup's "remove
        # anonymous perms while unpublished" branch does not fire either.
        resource.set_permissions(_build_public_perm_spec(resource))
    else:
        resource.set_permissions()
    # The advanced workflow (ADMIN_MODERATE_UPLOADS + RESOURCE_PUBLISHING)
    # strips the owner's edit rights on approved/published resources during
    # every set_permissions() call.  Restore them so the resource does not
    # appear to be "taken over by admin" after approval/publication.
    _restore_owner_perms(resource, owner_perms)


def _approve_data_collection(user, map_resource: Map, requesting_user=None):
    # Authorization happens at the endpoint via can_approve_data_collection()
    # (group-role gate).  Data stewards approve resources owned by *other*
    # users, so no per-resource guardian permission is required here.
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
    # Approving is allowed for any member (member or manager role) of an allowed
    # DataCite group; publishing is restricted to group managers (see publish endpoint).
    if not request.user.is_authenticated:
        raise PermissionDenied(_("Authentication required"))
    if not request.user.can_approve_data_collection():
        raise PermissionDenied(_("Permission Denied"))
    map = get_object_or_404(Map, id=mapid)

    # The owner field is used only to filter which linked resources to approve.
    owner_id = request.data.get("owner")
    if not owner_id:
        raise BadRequest("Owner ID is required")
    owner = _get_owner(id=owner_id)

    return _approve_data_collection(owner, map_resource=map, requesting_user=request.user)


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

    # Authorization happens at the endpoint via can_publish_data_collection()
    # (manager-role gate).  Data stewards publish resources owned by *other*
    # users, so no per-resource guardian permission is required here.
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

        # Assign the same bare DOI (e.g. "10.20387/...") to every resource in the collection
        for resource in resources:
            resource.doi = collection_doi
            resource.save(update_fields=["doi"])
            logger.info(
                f"Assigned collection DOI '{collection_doi}' to resource '{resource.title}' (ID: {resource.id})"
            )
    else:
        raise ValidationError(_("DOI prefix is required"))

    for resource in to_publish:
        _update_resource_status(resource, is_published=True)

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

    try:
        return _publish_data_collection(map, payload, user=user)
    except ValidationError as e:
        # Django's ValidationError is not handled by DRF's exception handler
        # and would surface as a 500 — translate it to a 422 with the message.
        messages = getattr(e, "messages", None) or [str(e)]
        return Response({"success": False, "message": "; ".join(messages)}, status=422)


# ---------------------------------------------------------------------------
# Sync metadata
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@authentication_classes(allowed_authentication_classes)
def sync_metadata_view(request, mapid):
    """
    GET  /api/v2/maps/<mapid>/sync_metadata/
         Returns a diff of all syncable metadata fields between the map and
         each linked resource.  Pass ?resource_pk=<pk> to limit to one resource.

    POST /api/v2/maps/<mapid>/sync_metadata/
         Syncs metadata from the map to its linked resources.
         Optional JSON body:
           - "resource_pk" (int) — target a single resource
           - "field_names" (list[str]) — sync only specific fields
         Requires change_resourcebase permission on the map.
    """
    map_obj = get_object_or_404(Map, id=mapid)

    # Resolve target resource(s)
    resource_pk = (
        request.query_params.get("resource_pk") if request.method == "GET" else (request.data or {}).get("resource_pk")
    )

    if resource_pk:
        try:
            from geonode.base.models import ResourceBase

            resources = [ResourceBase.objects.get(pk=int(resource_pk)).get_real_instance()]
        except Exception:
            return Response({"error": f"Resource {resource_pk} not found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        resources = get_syncable_resources(map_obj)

    if request.method == "GET":
        result = []
        for resource in resources:
            diffs = compare_metadata(map_obj, resource)
            result.append(
                {
                    "resource_pk": resource.pk,
                    "resource_title": resource.title,
                    "resource_type": resource.resource_type,
                    "diffs": diffs,
                }
            )
        return Response(result)

    # POST — perform the sync
    if not request.user.is_authenticated:
        raise PermissionDenied(_("Authentication required"))
    if not request.user.has_perm("base.change_resourcebase", map_obj.resourcebase_ptr):
        raise PermissionDenied(_("You do not have permission to sync metadata for this map."))

    field_names = (request.data or {}).get("field_names", None)
    if field_names is not None and not isinstance(field_names, list):
        return Response({"error": "'field_names' must be a list."}, status=status.HTTP_400_BAD_REQUEST)

    synced = []
    errors = []
    for resource in resources:
        try:
            sync_metadata(map_obj, resource, field_names=field_names)
            synced.append({"resource_pk": resource.pk, "resource_title": resource.title})
        except Exception as exc:
            logger.exception("Error syncing metadata to resource %s", resource.pk)
            errors.append({"resource_pk": resource.pk, "error": str(exc)})

    return Response({"synced": synced, "errors": errors}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# DataCite metadata download
# ---------------------------------------------------------------------------


@api_view(["GET"])
@authentication_classes(allowed_authentication_classes)
def datacite_metadata_view(request, pk):
    resource = get_object_or_404(ResourceBase, pk=pk)
    xml = get_datacite_xml(resource)
    if not xml:
        return Response({"detail": "DataCite XML not available."}, status=status.HTTP_404_NOT_FOUND)
    return HttpResponse(xml, content_type="application/xml")


@api_view(["GET"])
@authentication_classes(allowed_authentication_classes)
def datacite_prefixes_view(request):
    if not request.user.is_authenticated:
        raise PermissionDenied(_("Authentication required"))
    prefixes = get_doi_prefixes_for_user(request.user)
    return Response({"prefixes": prefixes})
