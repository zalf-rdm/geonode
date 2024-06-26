# Generated by Django 3.2.18 on 2023-03-31 08:33

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0092_alter_resourcebase_conformity_explanation'),
    ]

    operations = [
        migrations.AddField(
            model_name='resourcebase',
            name='parent_identifier',
            field=models.ForeignKey(blank=True, help_text='A file identifier of the metadata to which this metadata is a subset (child). (e.g. 73c0f49f-1502-48ee-b038-052563f36527)', null=True, on_delete=django.db.models.deletion.SET_NULL, to='base.resourcebase'),
        ),
    ]
