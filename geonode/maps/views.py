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
import logging

from django.contrib import messages as django_messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_exempt

from geonode.base import register_event
from geonode.base.auth import get_or_create_token
from geonode.base.enumerations import EventType
from geonode.maps.contants import (
    _PERMISSION_MSG_GENERIC,
    _PERMISSION_MSG_VIEW,
    MSG_NOT_ALLOWED,
    MSG_NOT_FOUND,
)
from geonode.maps.models import Map
from geonode.maps.utils import compare_metadata, get_all_syncable_fields, get_syncable_resources, sync_metadata
from geonode.utils import resolve_object

logger = logging.getLogger("geonode.maps.views")


def _resolve_map(request, id, permission="base.change_resourcebase", msg=_PERMISSION_MSG_GENERIC, **kwargs):
    """
    Resolve the Map by the provided typename and check the optional permission.
    """
    key = "urlsuffix" if Map.objects.filter(urlsuffix=id).exists() else "pk"

    map_obj = resolve_object(request, Map, {key: id}, permission=permission, permission_msg=msg, **kwargs)
    return map_obj


@xframe_options_exempt
def map_embed(request, mapid=None, template="maps/map_embed.html"):
    try:
        map_obj = _resolve_map(request, mapid, "base.view_resourcebase", _PERMISSION_MSG_VIEW)
    except PermissionDenied:
        return HttpResponse(MSG_NOT_ALLOWED, status=403)
    except Exception:
        raise Http404(MSG_NOT_FOUND)

    if not map_obj:
        raise Http404(MSG_NOT_FOUND)

    access_token = None
    if request and request.user:
        access_token = get_or_create_token(request.user)
        if access_token and not access_token.is_expired():
            access_token = access_token.token
        else:
            access_token = None

    context_dict = {
        "access_token": access_token,
        "resource": map_obj,
    }

    register_event(request, EventType.EVENT_VIEW, map_obj)
    return render(request, template, context=context_dict)


def map_metadata_sync(request, mapid, template="maps/map_metadata_sync.html"):
    """
    Compare metadata between a map and its linked resources, and optionally
    sync (patch) the map's metadata to selected resources.
    Accessible to any user with change_resourcebase_metadata on the map.
    """
    if not request.user.is_authenticated:
        return HttpResponse(MSG_NOT_ALLOWED, status=403)

    try:
        map_obj = _resolve_map(request, mapid, "base.change_resourcebase_metadata", _PERMISSION_MSG_GENERIC)
    except PermissionDenied:
        return HttpResponse(MSG_NOT_ALLOWED, status=403)
    except Exception:
        raise Http404(MSG_NOT_FOUND)
    if not map_obj:
        raise Http404(MSG_NOT_FOUND)

    resources = get_syncable_resources(map_obj)
    all_fields = get_all_syncable_fields()

    if request.method == "POST":
        selected_ids = request.POST.getlist("resource_ids")
        selected_field_names = request.POST.getlist("field_names")
        if selected_ids:
            try:
                selected_ids = [int(rid) for rid in selected_ids]
            except (ValueError, TypeError):
                django_messages.error(request, "Invalid resource selection.")
                return HttpResponseRedirect(reverse("map_metadata_sync", kwargs={"mapid": mapid}))
            synced_count = 0
            for res in resources:
                if res.pk in selected_ids:
                    try:
                        sync_metadata(map_obj, res, field_names=selected_field_names)
                        synced_count += 1
                    except Exception:
                        logger.exception("Failed to sync metadata to resource %s", res.pk)
                        django_messages.error(request, f"Failed to sync metadata to: {res.title}")
            django_messages.success(
                request,
                f"Successfully synced metadata to {synced_count} resource(s).",
            )
        else:
            django_messages.warning(request, "No resources were selected for sync.")
        return HttpResponseRedirect(reverse("map_metadata_sync", kwargs={"mapid": mapid}))

    # GET: build comparison data
    comparison_data = []
    total_diffs = 0
    for res in resources:
        diffs = compare_metadata(map_obj, res)
        diff_count = sum(1 for d in diffs if not d["match"])
        total_diffs += diff_count
        metadata_url = f"/catalogue/#/metadata/{res.pk}"
        comparison_data.append(
            {
                "resource": res,
                "diffs": diffs,
                "diff_count": diff_count,
                "metadata_url": metadata_url,
            }
        )

    return render(
        request,
        template,
        context={
            "map": map_obj,
            "resource": map_obj,
            "resources": resources,
            "comparison_data": comparison_data,
            "total_diffs": total_diffs,
            "all_fields": all_fields,
        },
    )
