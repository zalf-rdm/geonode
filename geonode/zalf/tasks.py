import logging

from celery import shared_task
from django.db.models import F
from django.utils import timezone

from geonode.layers.models import Dataset
from geonode.zalf.delivery_audit import DatasetDeliveryAuditor, DeliveryAuditUnavailable
from geonode.zalf.models import DatasetDeliveryAudit

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="geonode.zalf.tasks.audit_dataset_delivery",
    queue="geoserver.catalog",
    acks_late=False,
    time_limit=300,
    autoretry_for=(DeliveryAuditUnavailable,),
    retry_kwargs={"max_retries": 4},
    retry_backoff=10,
    retry_backoff_max=120,
    retry_jitter=False,
)
def audit_dataset_delivery(self, dataset_id):
    """Run an idempotent audit; repeated task delivery updates one record."""
    try:
        dataset = Dataset.objects.select_related("default_style").get(pk=dataset_id)
    except Dataset.DoesNotExist:
        logger.info("delivery_audit dataset=%s status=skipped reason=deleted", dataset_id)
        return {"dataset_id": dataset_id, "status": "skipped", "reason": "deleted"}

    audit, _ = DatasetDeliveryAudit.objects.get_or_create(dataset=dataset)
    if not dataset.is_published or not dataset.is_approved:
        result = {
            "schema_version": 1,
            "dataset_id": dataset_id,
            "status": "skipped",
            "reason": "dataset is not both approved and published",
        }
        audit.status = DatasetDeliveryAudit.Status.SKIPPED
        audit.result = result
        audit.finished_at = timezone.now()
        audit.save(update_fields=["status", "result", "finished_at", "updated_at"])
        logger.info("delivery_audit dataset=%s status=skipped reason=private", dataset_id)
        return result

    if dataset.subtype not in {"vector", "vector_time", "raster"}:
        result = {
            "schema_version": 1,
            "dataset_id": dataset_id,
            "status": "skipped",
            "reason": f"non-spatial subtype: {dataset.subtype}",
        }
        audit.status = DatasetDeliveryAudit.Status.SKIPPED
        audit.result = result
        audit.finished_at = timezone.now()
        audit.save(update_fields=["status", "result", "finished_at", "updated_at"])
        logger.info("delivery_audit dataset=%s status=skipped reason=non-spatial", dataset_id)
        return result

    DatasetDeliveryAudit.objects.filter(pk=audit.pk).update(
        status=DatasetDeliveryAudit.Status.RUNNING,
        started_at=timezone.now(),
        finished_at=None,
        attempt_count=F("attempt_count") + 1,
    )
    try:
        result = DatasetDeliveryAuditor(dataset).run()
    except DeliveryAuditUnavailable as exc:
        DatasetDeliveryAudit.objects.filter(pk=audit.pk).update(
            status=DatasetDeliveryAudit.Status.PENDING,
            result={"schema_version": 1, "dataset_id": dataset_id, "status": "retrying", "reason": str(exc)},
        )
        logger.warning("delivery_audit dataset=%s status=retrying reason=%s", dataset_id, exc)
        raise

    final_status = (
        DatasetDeliveryAudit.Status.PASSED if result["status"] == "passed" else DatasetDeliveryAudit.Status.FAILED
    )
    DatasetDeliveryAudit.objects.filter(pk=audit.pk).update(
        status=final_status,
        result=result,
        finished_at=timezone.now(),
    )
    logger.info(
        "delivery_audit dataset=%s layer=%s status=%s failed_checks=%s",
        dataset_id,
        result.get("layer"),
        result["status"],
        result.get("failed_checks", []),
    )
    return result
