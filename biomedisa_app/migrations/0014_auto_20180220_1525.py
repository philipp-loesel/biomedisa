# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-02-20 14:25
from __future__ import unicode_literals

import biomedisa_app.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0013_upload_active_contours'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='upload',
            name='allxis',
        ),
        migrations.RemoveField(
            model_name='upload',
            name='cleanup',
        ),
        migrations.RemoveField(
            model_name='upload',
            name='friendAC',
        ),
        migrations.RemoveField(
            model_name='upload',
            name='grid',
        ),
        migrations.RemoveField(
            model_name='upload',
            name='parameters',
        ),
        migrations.AddField(
            model_name='upload',
            name='active',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='upload',
            name='delete_outliers',
            field=models.FloatField(default=0.9),
        ),
        migrations.AddField(
            model_name='upload',
            name='fill_wholes',
            field=models.FloatField(default=0.9),
        ),
        migrations.AlterField(
            model_name='upload',
            name='ac_alpha',
            field=models.FloatField(default=1.0, verbose_name='Active contours alpha'),
        ),
        migrations.AlterField(
            model_name='upload',
            name='ac_smooth',
            field=models.IntegerField(default=1, verbose_name='Active contours smooth'),
        ),
        migrations.AlterField(
            model_name='upload',
            name='ac_steps',
            field=models.IntegerField(default=3, verbose_name='Active contours steps'),
        ),
        migrations.AlterField(
            model_name='upload',
            name='active_contours',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='upload',
            name='allaxis',
            field=models.BooleanField(default=False, verbose_name='All axis'),
        ),
        migrations.AlterField(
            model_name='upload',
            name='pic',
            field=models.FileField(upload_to=biomedisa_app.models.user_directory_path, verbose_name=''),
        ),
    ]
