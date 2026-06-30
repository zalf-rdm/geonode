from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('zalf', '0001_cms_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingresource',
            name='duration',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
    ]
