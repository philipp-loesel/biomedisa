# Generated by Django 2.1.5 on 2019-03-13 08:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0036_auto_20190312_1945'),
    ]

    operations = [
        migrations.AlterField(
            model_name='upload',
            name='only',
            field=models.CharField(default='all', max_length=20, verbose_name='compute only label'),
        ),
    ]