# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-05-22 13:23
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0020_auto_20180518_1549'),
    ]

    operations = [
        migrations.AddField(
            model_name='upload',
            name='predict',
            field=models.BooleanField(default=False, verbose_name='Predict'),
        ),
        migrations.AlterField(
            model_name='upload',
            name='cnn',
            field=models.BooleanField(default=False, verbose_name='Train'),
        ),
    ]
