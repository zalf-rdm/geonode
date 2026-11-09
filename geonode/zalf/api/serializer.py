from rest_framework import serializers


class PublishSerializer(serializers.Serializer):

    owner = serializers.IntegerField()
    resources = serializers.ListField(child=serializers.IntegerField(min_value=1))
    doi_prefix = serializers.CharField(required=False)
    # Queue the download package build after publication (zalf-rdm/geonode#659).
    build_download_package = serializers.BooleanField(required=False, default=True)
