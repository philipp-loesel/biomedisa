# Generated by Django 2.2.2 on 2019-08-19 13:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0046_auto_20190819_1515'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='upload',
            name='stride_size_refining',
        ),
    ]
