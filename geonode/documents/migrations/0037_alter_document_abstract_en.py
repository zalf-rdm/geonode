# Generated by Django 3.2.18 on 2023-03-30 06:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0036_clean_document_thumbnails'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='abstract_en',
            field=models.TextField(help_text='brief narrative summary of the content of the resource(s)', max_length=2000, null=True, verbose_name='abstract'),
        ),
    ]