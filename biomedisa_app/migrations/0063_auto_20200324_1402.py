# Generated by Django 3.0.4 on 2020-03-24 13:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biomedisa_app', '0062_auto_20200324_1401'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mushroomspot',
            name='status_klopapier',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='mushroomspot',
            name='status_mehl',
            field=models.TextField(null=True),
        ),
        migrations.AlterField(
            model_name='mushroomspot',
            name='status_nudeln',
            field=models.TextField(null=True),
        ),
    ]
