from rest_framework import serializers
from geonode.maps.models import MapLayer


class PublishSerializer(serializers.Serializer):

    # map layers are included in linked resources
    # map_layers = serializers.ListField(
    #     child=serializers.IntegerField(min_value=1)
    # )
    linked_resources = serializers.ListField(
        child=serializers.IntegerField(min_value=1)
    )
    doi_prefix = serializers.CharField()
