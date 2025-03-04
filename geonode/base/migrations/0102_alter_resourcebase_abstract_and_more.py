# Generated by Django 4.2.9 on 2024-11-28 08:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0101_merge_20240924_1415"),
    ]

    operations = [
        migrations.AlterField(
            model_name="resourcebase",
            name="abstract",
            field=models.CharField(
                help_text="brief narrative summary of the content of the resource(s)",
                max_length=6000,
                verbose_name="Abstract",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="conformity_explanation",
            field=models.CharField(
                blank=True,
                help_text="Give an Explanation about the conformity check. (e.g. See the referenced specification.",
                max_length=4000,
                verbose_name="Conformity Explanation",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="method_description",
            field=models.TextField(
                blank=True,
                help_text="The methodology employed for the study or research",
                max_length=6000,
                verbose_name="Method Description",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="other_description",
            field=models.TextField(
                blank=True,
                help_text="Other description information that does not fit into an existing category",
                max_length=6000,
                verbose_name="Other Description",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="purpose",
            field=models.TextField(
                blank=True,
                help_text="summary of the intentions with which the resource(s) was developed",
                max_length=1024,
                null=True,
                verbose_name="Purpose",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="series_information",
            field=models.TextField(
                blank=True,
                help_text="Information about a repeating series, such as volumne, issue, number",
                max_length=6000,
                verbose_name="Series Information",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="subtitle",
            field=models.TextField(
                blank=True, help_text="subtitle of the dataset", max_length=1024, verbose_name="Subtitle"
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="table_of_content",
            field=models.TextField(
                blank=True,
                help_text="A listing of the Table of Contents",
                max_length=6000,
                verbose_name="Table of Content",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="technical_info",
            field=models.TextField(
                blank=True,
                help_text="Detailed information that may be associated with design, implementation, operation, use, and/or maintenance of a process or system",
                max_length=6000,
                verbose_name="Technical Info",
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="title",
            field=models.CharField(
                help_text="name by which the cited resource is known", max_length=512, verbose_name="Title"
            ),
        ),
        migrations.AlterField(
            model_name="resourcebase",
            name="title_translated",
            field=models.CharField(
                blank=True,
                help_text="german name by which the cited resource is known",
                max_length=512,
                verbose_name="Title Translated",
            ),
        ),
    ]
