import uuid

from django.db import models
from django.contrib.auth import get_user_model

from geonode.maps.models import Map

class DataCollectionStatus(models.Model):

    approval_code = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submittor = models.ForeignKey(
        get_user_model(), related_name="submittor", null=False, blank=False, on_delete=models.CASCADE
    )
    data_steward = models.ForeignKey(
        get_user_model(), related_name="data_steward", null=False, blank=False, on_delete=models.CASCADE
    )
    map = models.ForeignKey(Map, null=False, blank=False, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now=True, blank=False, null=False,)
    approved_at = models.DateTimeField(blank=True, null=True,)
    published_at = models.DateTimeField(blank=True, null=True,)
