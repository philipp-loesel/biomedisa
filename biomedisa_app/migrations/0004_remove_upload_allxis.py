# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-05-17 10:12
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0003_auto_20170517_1159'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='upload',
            name='allxis',
        ),
    ]