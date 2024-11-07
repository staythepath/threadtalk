# Generated by Django 5.1.2 on 2024-11-07 05:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activitypub', '0002_localactor_community_description_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='localactor',
            name='inbox',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='localactor',
            name='outbox',
            field=models.URLField(blank=True, null=True),
        ),
    ]
