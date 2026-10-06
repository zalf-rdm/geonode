from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from geonode.layers.models import Dataset
from geonode.zalf.delivery_audit_scheduler import schedule_delivery_audit


@receiver(pre_save, sender=Dataset)
def remember_dataset_delivery_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._zalf_delivery_was_ready = False
        return
    previous = sender.objects.filter(pk=instance.pk).values("is_published", "is_approved").first()
    instance._zalf_delivery_was_ready = bool(previous and previous["is_published"] and previous["is_approved"])


@receiver(post_save, sender=Dataset)
def schedule_dataset_delivery_on_publication(sender, instance, **kwargs):
    ready = bool(instance.is_published and instance.is_approved)
    if ready and not getattr(instance, "_zalf_delivery_was_ready", False):
        schedule_delivery_audit(instance)
