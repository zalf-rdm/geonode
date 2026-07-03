from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('zalf', '0002_training_duration'),
    ]

    operations = [
        migrations.AddField(
            model_name='trainingresource',
            name='category',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AddField(
            model_name='trainingresource',
            name='format',
            field=models.CharField(
                blank=True,
                choices=[
                    ('on-demand', 'On-demand / Self-paced'),
                    ('video', 'Recorded video'),
                    ('live', 'Live webinar'),
                    ('workshop', 'In-person workshop'),
                ],
                default='',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='trainingresource',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trainingresource',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trainingresource',
            name='course_url',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
