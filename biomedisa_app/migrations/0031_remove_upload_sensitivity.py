# Generated by Django 2.1.5 on 2019-01-25 10:31

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0030_auto_20190123_1815'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='upload',
            name='sensitivity',
        ),
    ]
