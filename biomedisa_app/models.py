##########################################################################
##                                                                      ##
##  Copyright (c) 2020 Philipp Lösel. All rights reserved.              ##
##                                                                      ##
##  This file is part of the open source project biomedisa.             ##
##                                                                      ##
##  Licensed under the European Union Public Licence (EUPL)             ##
##  v1.2, or - as soon as they will be approved by the                  ##
##  European Commission - subsequent versions of the EUPL;              ##
##                                                                      ##
##  You may redistribute it and/or modify it under the terms            ##
##  of the EUPL v1.2. You may not use this work except in               ##
##  compliance with this Licence.                                       ##
##                                                                      ##
##  You can obtain a copy of the Licence at:                            ##
##                                                                      ##
##  https://joinup.ec.europa.eu/page/eupl-text-11-12                    ##
##                                                                      ##
##  Unless required by applicable law or agreed to in                   ##
##  writing, software distributed under the Licence is                  ##
##  distributed on an "AS IS" basis, WITHOUT WARRANTIES                 ##
##  OR CONDITIONS OF ANY KIND, either express or implied.               ##
##                                                                      ##
##  See the Licence for the specific language governing                 ##
##  permissions and limitations under the Licence.                      ##
##                                                                      ##
##########################################################################

from __future__ import unicode_literals

from django.db import models
from django import forms
from django.contrib.auth.models import User
from biomedisa_app.config import config
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.contrib.auth.password_validation import validate_password
from django.core.files.storage import FileSystemStorage
import shutil
import os

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    storage_size = models.IntegerField(default=100)
    notification = models.BooleanField(default=True)
    activation_key = models.TextField(null=True)
    key_expires = models.DateTimeField(null=True)

class UserForm(forms.ModelForm):
    notification = forms.BooleanField(required=False)
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'notification')

def user_directory_path(instance, filename):
    filename = filename.encode('ascii', 'ignore').decode()
    filename = os.path.basename(filename)
    filename, extension = os.path.splitext(filename)
    filename = 'images/%s/%s' %(instance.user, filename)
    limit = 100 - len(extension)
    filename = filename[:limit] + extension
    return filename

class CustomUserCreationForm(forms.Form):
    alphanumeric = RegexValidator(r'^[0-9a-zA-Z]*$', 'Only alphanumeric characters are allowed.')
    username = forms.CharField(label='Username', min_length=4, max_length=12, validators=[alphanumeric])
    email = forms.EmailField(label='Email')
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)
    institution = forms.CharField(label='Institution')
    subject = forms.CharField(label='Subject of research')
    message = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 8, 'cols': 50}))

    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        validation = validate_password(password1)
        if validation:
            raise validation
        return password1

    def clean_username(self):
        username = self.cleaned_data['username'].lower()
        r = User.objects.filter(username=username)
        if r.count():
            raise ValidationError("Username already exists")
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        r = User.objects.filter(email=email)
        if r.count():
            raise ValidationError("Email already exists")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("Password doesn't match")
        return password2

    def clean_subject(self):
        subject = self.cleaned_data.get('subject')
        institution = self.cleaned_data.get('institution')
        if institution == subject:
            raise ValidationError("Institute and subject must be different")
        return subject

    def save(self, datas, commit=True):
        user = User.objects.create_user(
            self.cleaned_data['username'],
            self.cleaned_data['email'],
            self.cleaned_data['password1'],
            is_active=datas['is_active'],
            is_superuser=False,
            is_staff=False
            )
        profile = Profile()
        profile.user = user
        profile.activation_key = datas['activation_key']
        profile.key_expires = datas['key_expires']
        profile.save()
        return self.cleaned_data

class Upload(models.Model):
    private_storage = FileSystemStorage(location=config['PATH_TO_BIOMEDISA'] + '/private_storage/')
    pic = models.FileField("", upload_to=user_directory_path, storage=private_storage)
    upload_date = models.DateTimeField(auto_now_add=True, null=True)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    CHOICES = zip( range(1,10), range(1,10) )
    project = models.IntegerField(choices=CHOICES, default=1)
    CHOICES = ( (1,'Image'), (2,'Label'), (4,'Network') )
    imageType = models.IntegerField("Type", choices=CHOICES, default=1, null=True)
    final = models.IntegerField(default=0)
    active = models.IntegerField(default=0)
    status = models.IntegerField(default=0)
    log = models.IntegerField(default=0)
    shortfilename = models.TextField(null=True)
    job_id = models.TextField(null=True)
    message = models.TextField(null=True)
    nbrw = models.IntegerField(default=10)
    sorw = models.IntegerField(default=4000)
    hashed = models.TextField(null=True)
    hashed2 = models.TextField(null=True)
    size = models.IntegerField(default=0)
    shared = models.IntegerField(default=0)
    shared_by = models.TextField(null=True)
    shared_path = models.TextField(null=True)
    friend = models.IntegerField(default=None, null=True)
    allaxis = models.BooleanField("All axes", default=False)
    diffusion = models.BooleanField(default=True)
    smooth = models.IntegerField(default=100)
    active_contours = models.BooleanField(default=True)
    ac_alpha = models.FloatField("Active contour alpha", default=1.0)
    ac_smooth = models.IntegerField("Active contour smooth", default=1)
    ac_steps = models.IntegerField("Active contour steps", default=3)
    delete_outliers = models.FloatField(default=0.9)
    fill_holes = models.FloatField(default=0.9)
    ignore = models.CharField("ignore label", default='none', max_length=20)
    predict = models.BooleanField("Predict", default=False)
    pid = models.IntegerField(default=0)
    normalize = models.BooleanField("Normalize training data (AI)", default=True)
    compression = models.BooleanField(default=True)
    epochs = models.IntegerField("Number of epochs (AI)", default=200)
    inverse = models.BooleanField(default=False)
    only = models.CharField("compute only label", default='all', max_length=20)
    position = models.BooleanField("Consider voxel location (AI)", default=False)
    full_size = models.BooleanField("Full size preview", default=False)
    stride_size = models.IntegerField("Stride size (AI)", default=32)
    queue = models.IntegerField(default=1)
    x_scale = models.IntegerField("X Scale (AI)", default=256)
    y_scale = models.IntegerField("Y Scale (AI)", default=256)
    z_scale = models.IntegerField("Z Scale (AI)", default=256)
    balance = models.BooleanField("Balance training data (AI)", default=False)
    uncertainty = models.BooleanField(default=True)
    batch_size = models.IntegerField("Batch size (AI)", default=24)

class UploadForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ('pic', 'project', 'imageType')

class StorageForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ('pic','imageType')

class SettingsForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ('allaxis', 'uncertainty', 'compression', 'normalize', \
                  'position', 'balance', 'epochs', 'batch_size', 'x_scale', 'y_scale', 'z_scale', \
                  'stride_size', 'smooth', 'ac_alpha', 'ac_smooth', 'ac_steps', \
                  'delete_outliers', 'fill_holes', 'ignore', 'only')

class SettingsPredictionForm(forms.ModelForm):
    class Meta:
        model = Upload
        fields = ('compression', 'batch_size', 'stride_size', 'delete_outliers', 'fill_holes', \
                  'ac_alpha', 'ac_smooth', 'ac_steps')

@receiver(models.signals.post_delete, sender=Upload)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Deletes file from filesystem
    when corresponding `Upload` object is deleted.
    """
    if instance.pic:

        path_to_slicemaps = instance.pic.path.replace('images', 'dataset', 1)
        if os.path.isdir(path_to_slicemaps):
            shutil.rmtree(path_to_slicemaps)

        path_to_slices = instance.pic.path.replace('images', 'sliceviewer', 1)
        if os.path.isdir(path_to_slices):
            shutil.rmtree(path_to_slices)

        if instance.pic.path[-4:] in ['.tar', '.zip'] and os.path.isdir(instance.pic.path[:-4]):
            shutil.rmtree(instance.pic.path[:-4])

        if os.path.isfile(instance.pic.path):
            os.remove(instance.pic.path)
        elif os.path.isdir(instance.pic.path):
            shutil.rmtree(instance.pic.path)
