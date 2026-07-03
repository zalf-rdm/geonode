from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='HighlightedCase',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tab_label', models.CharField(max_length=40)),
                ('eyebrow', models.CharField(default='HIGHLIGHTED CASE', max_length=60)),
                ('title', models.CharField(max_length=160)),
                ('button_text', models.CharField(default='View case', max_length=40)),
                ('href', models.CharField(max_length=500)),
                ('image', models.ImageField(blank=True, null=True, upload_to='cms/cases/')),
                ('body_markdown', models.TextField(blank=True)),
                ('slug', models.SlugField(blank=True, unique=True)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='SpotlightBanner',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kicker', models.CharField(max_length=80)),
                ('title', models.CharField(max_length=120)),
                ('description', models.CharField(blank=True, max_length=240)),
                ('button_text', models.CharField(max_length=40)),
                ('href', models.CharField(max_length=500)),
                ('image', models.ImageField(blank=True, null=True, upload_to='cms/banners/')),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='TrainingResource',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=160)),
                ('organizer', models.CharField(max_length=120)),
                ('thumbnail', models.ImageField(blank=True, null=True, upload_to='cms/training/')),
                ('body_markdown', models.TextField(blank=True)),
                ('slug', models.SlugField(blank=True, unique=True)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['order'],
            },
        ),
    ]
