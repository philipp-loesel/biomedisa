# Generated by Django 2.2.2 on 2019-08-19 14:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0048_upload_heart'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='storage_size',
            field=models.IntegerField(default=100),
        ),
    ]
