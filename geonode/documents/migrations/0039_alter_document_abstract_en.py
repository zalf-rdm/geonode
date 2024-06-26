# Generated by Django 3.2.23 on 2024-06-18 14:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0038_alter_document_doc_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='abstract_en',
            field=models.TextField(help_text='brief narrative summary of the content of the resource(s)', max_length=2000, null=True, verbose_name='abstract'),
        ),
    ]
