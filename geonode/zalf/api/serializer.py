from rest_framework import serializers


class PublishSerializer(serializers.Serializer):

    owner = serializers.IntegerField()
    resources = serializers.ListField(
        child=serializers.IntegerField(min_value=1)
    )
    doi_prefix = serializers.CharField(required=False)
