from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_twofactorsettings_secret'),
    ]

    operations = [
        migrations.CreateModel(
            name='BackgroundJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_id', models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ('task_name', models.CharField(max_length=128)),
                ('queue_name', models.CharField(default='celery', max_length=64)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('success', 'Success'), ('failed', 'Failed'), ('retried', 'Retried')], default='pending', max_length=16)),
                ('retries', models.PositiveIntegerField(default=0)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('result_text', models.TextField(blank=True)),
                ('failure_reason', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('execution_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('last_retry_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('triggered_by', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
