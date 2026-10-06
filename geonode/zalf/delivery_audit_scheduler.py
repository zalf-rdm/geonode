from django.db import transaction
from django.utils import timezone

from geonode.zalf.models import DatasetDeliveryAudit


def schedule_delivery_audit(dataset):
    """Persist pending state and enqueue only after the surrounding commit."""
    if not dataset.is_published or not dataset.is_approved:
        return False
    if dataset.subtype not in {"vector", "vector_time", "raster"}:
        return False

    audit, created = DatasetDeliveryAudit.objects.get_or_create(
        dataset=dataset,
        defaults={"status": DatasetDeliveryAudit.Status.PENDING, "scheduled_at": timezone.now()},
    )
    if not created and audit.status in {DatasetDeliveryAudit.Status.PENDING, DatasetDeliveryAudit.Status.RUNNING}:
        return False
    if not created:
        audit.status = DatasetDeliveryAudit.Status.PENDING
        audit.scheduled_at = timezone.now()
        audit.finished_at = None
        audit.save(update_fields=["status", "scheduled_at", "finished_at", "updated_at"])

    dataset_id = dataset.pk

    def enqueue():
        from geonode.zalf.tasks import audit_dataset_delivery

        audit_dataset_delivery.apply_async(args=[dataset_id], queue="geoserver.catalog")

    transaction.on_commit(enqueue)
    return True
