# Generated by Django 2.1.5 on 2019-02-15 08:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0033_auto_20190214_1457'),
    ]

    operations = [
        migrations.AlterField(
            model_name='upload',
            name='inverse_steps',
            field=models.IntegerField(default=50, verbose_name='Inverse steps'),
        ),
    ]