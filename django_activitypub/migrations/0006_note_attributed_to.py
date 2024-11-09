# Generated by Django 5.1.2 on 2024-11-09 07:46

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activitypub', '0005_localactor_created_at_localactor_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='attributed_to',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='activitypub.localactor'),
        ),
    ]
