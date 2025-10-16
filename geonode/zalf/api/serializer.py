from rest_framework import serializers
from geonode.maps.models import MapLayer


class PublishSerializer(serializers.Serializer):

    resources = serializers.ListField(
        child=serializers.IntegerField(min_value=1)
    )
    doi_prefix = serializers.CharField()
