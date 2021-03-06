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

from biomedisa_features.biomedisa_helper import img_resize, load_data, save_data
from keras.optimizers import SGD
from keras.models import Model, load_model
from keras.layers import (
    Input, Conv3D, MaxPooling3D, UpSampling3D, Activation, Reshape,
    BatchNormalization, Concatenate)
from keras.utils import multi_gpu_model, to_categorical
import numpy as np
import cv2
from random import shuffle
from glob import glob
import random
import numba
import re
import os

class InputError(Exception):
    def __init__(self, message=None):
        self.message = message

def adjust_header(header, data):

    # read header as string
    b = header.tobytes()
    s = b.decode("utf-8")

    # get image size in header
    lattice = re.search('define Lattice (.*)\n', s)
    lattice = lattice.group(1)
    xsh, ysh, zsh = lattice.split(' ')
    xsh, ysh, zsh = int(xsh), int(ysh), int(zsh)

    # new image size
    z,y,x = data.shape

    # change image size in header
    s = s.replace('%s %s %s' %(xsh,ysh,zsh), '%s %s %s' %(x,y,z),1)
    s = s.replace('Content "%sx%sx%s byte' %(xsh,ysh,zsh), 'Content "%sx%sx%s byte' %(x,y,z),1)

    # return header as array
    b2 = s.encode()
    new_header = np.frombuffer(b2, dtype=data.dtype)
    return new_header

@numba.jit(nopython=True)
def compute_position(position, zsh, ysh, xsh):
    zsh_h, ysh_h, xsh_h = zsh//2, ysh//2, xsh//2
    for k in range(zsh):
        for l in range(ysh):
            for m in range(xsh):
                x = (xsh_h-m)**2
                y = (ysh_h-l)**2
                z = (zsh_h-k)**2
                position[k,l,m] = x+y+z
    return position

def make_axis_divisible_by_patch_size(a, patch_size):
    zsh, ysh, xsh = a.shape
    a = np.append(a, np.zeros((patch_size-(zsh % patch_size), ysh, xsh), a.dtype), axis=0)
    zsh, ysh, xsh = a.shape
    a = np.append(a, np.zeros((zsh, patch_size-(ysh % patch_size), xsh), a.dtype), axis=1)
    zsh, ysh, xsh = a.shape
    a = np.append(a, np.zeros((zsh, ysh, patch_size-(xsh % patch_size)), a.dtype), axis=2)
    a = np.copy(a, order='C')
    return a

def make_conv_block(nb_filters, input_tensor, block):
    def make_stage(input_tensor, stage):
        name = 'conv_{}_{}'.format(block, stage)
        x = Conv3D(nb_filters, (3, 3, 3), activation='relu',
                   padding='same', name=name, data_format="channels_last")(input_tensor)
        name = 'batch_norm_{}_{}'.format(block, stage)
        x = BatchNormalization(name=name)(x)
        x = Activation('relu')(x)
        return x

    x = make_stage(input_tensor, 1)
    x = make_stage(x, 2)
    return x

def make_unet(input_shape, nb_labels):

    nb_plans, nb_rows, nb_cols, _ = input_shape

    inputs = Input(input_shape)
    conv1 = make_conv_block(32, inputs, 1)
    pool1 = MaxPooling3D(pool_size=(2, 2, 2))(conv1)

    conv2 = make_conv_block(64, pool1, 2)
    pool2 = MaxPooling3D(pool_size=(2, 2, 2))(conv2)

    conv3 = make_conv_block(128, pool2, 3)
    pool3 = MaxPooling3D(pool_size=(2, 2, 2))(conv3)

    conv4 = make_conv_block(256, pool3, 4)
    pool4 = MaxPooling3D(pool_size=(2, 2, 2))(conv4)

    conv5 = make_conv_block(512, pool4, 5)

    up6 = Concatenate()([UpSampling3D(size=(2, 2, 2))(conv5), conv4])
    conv6 = make_conv_block(256, up6, 6)

    up7 = Concatenate()([UpSampling3D(size=(2, 2, 2))(conv6), conv3])
    conv7 = make_conv_block(128, up7, 7)

    up8 = Concatenate()([UpSampling3D(size=(2, 2, 2))(conv7), conv2])
    conv8 = make_conv_block(64, up8, 8)

    up9 = Concatenate()([UpSampling3D(size=(2, 2, 2))(conv8), conv1])
    conv9 = make_conv_block(32, up9, 9)

    conv10 = Conv3D(nb_labels, (1, 1, 1), name='conv_10_1')(conv9)

    x = Reshape((nb_plans * nb_rows * nb_cols, nb_labels))(conv10)
    x = Activation('softmax')(x)
    outputs = Reshape((nb_plans, nb_rows, nb_cols, nb_labels))(x)

    model = Model(inputs=inputs, outputs=outputs)

    return model

def get_labels(arr, allLabels):
    np_unique = np.unique(arr)
    final = np.zeros_like(arr)
    for k in np_unique:
        final[arr == k] = allLabels[k]
    return final

#=====================
# regular
#=====================

def load_training_data(normalize, img_list, label_list, channels, x_scale, y_scale, z_scale):

    # get filenames
    img_names, label_names = [], []
    for img_name, label_name in zip(img_list, label_list):
        if img_name[-4:] == '.tar' and label_name[-4:] == '.tar':
            for data_type in ['.am','.tif','.tiff','.hdr','.mhd','.mha','.nrrd','.nii','.nii.gz']:
                tmp_img_names = glob(img_name[:-4]+'/*/*'+data_type)+glob(img_name[:-4]+'/*'+data_type)
                tmp_label_names = glob(label_name[:-4]+'/*/*'+data_type)+glob(label_name[:-4]+'/*'+data_type)
                tmp_img_names = sorted(tmp_img_names)
                tmp_label_names = sorted(tmp_label_names)
                img_names.extend(tmp_img_names)
                label_names.extend(tmp_label_names)
        else:
            img_names.append(img_name)
            label_names.append(label_name)

    # load img data
    img, _ = load_data(img_names[0], 'first_queue')
    if img is None:
        InputError.message = "Invalid image data '%s.'" %(os.path.basename(img_names[0]))
        raise InputError()
    img = img.astype(np.float32)
    img = img_resize(img, z_scale, y_scale, x_scale)
    img -= np.amin(img)
    img /= np.amax(img)
    mu, sig = np.mean(img), np.std(img)
    for name in img_names[1:]:
        a, _ = load_data(name, 'first_queue')
        if a is None:
            InputError.message = "Invalid image data '%s.'" %(os.path.basename(name))
            raise InputError()
        a = a.astype(np.float32)
        a = img_resize(a, z_scale, y_scale, x_scale)
        a -= np.amin(a)
        a /= np.amax(a)
        if normalize:
            mu_tmp, sig_tmp = np.mean(a), np.std(a)
            a = (a - mu_tmp) / sig_tmp
            a = a * sig + mu
        img = np.append(img, a, axis=0)

    # scale to [0,1]
    img[img<0] = 0
    img[img>1] = 1

    # load label data
    a, header, extension = load_data(label_names[0], 'first_queue', True)
    if a is None:
        InputError.message = "Invalid label data '%s.'" %(os.path.basename(label_names[0]))
        raise InputError()
    a = a.astype(np.uint8)
    np_unique = np.unique(a)
    label = np.zeros((z_scale, y_scale, x_scale), dtype=a.dtype)
    for k in np_unique:
        tmp = np.zeros_like(a)
        tmp[a==k] = 1
        tmp = img_resize(tmp, z_scale, y_scale, x_scale)
        label[tmp==1] = k
    for name in label_names[1:]:
        a, _ = load_data(name, 'first_queue')
        if a is None:
            InputError.message = "Invalid label data '%s.'" %(os.path.basename(name))
            raise InputError()
        a = a.astype(np.uint8)
        np_unique = np.unique(a)
        next_label = np.zeros((z_scale, y_scale, x_scale), dtype=a.dtype)
        for k in np_unique:
            tmp = np.zeros_like(a)
            tmp[a==k] = 1
            tmp = img_resize(tmp, z_scale, y_scale, x_scale)
            next_label[tmp==1] = k
        label = np.append(label, next_label, axis=0)

    # compute position data
    position = None
    if channels == 2:
        position = np.empty((z_scale, y_scale, x_scale), dtype=np.float32)
        position = compute_position(position, z_scale, y_scale, x_scale)
        position = np.sqrt(position)
        position /= np.amax(position)
        for k in range(len(img_names[1:])):
            a = np.copy(position)
            position = np.append(position, a, axis=0)

    # labels must be in ascending order
    allLabels = np.unique(label)
    for k, l in enumerate(allLabels):
        label[label==l] = k

    return img, label, position, allLabels, mu, sig, header, extension

def config_training_data(img, label, position, z_patch, y_patch, x_patch, channels, stride_size, balance):

    if balance:

        # img shape
        zsh, ysh, xsh = img.shape

        # get number of patches
        nb_fg, nb_bg = 0, 0
        for k in range(0, zsh-z_patch+1, stride_size):
            for l in range(0, ysh-y_patch+1, stride_size):
                for m in range(0, xsh-x_patch+1, stride_size):
                    if np.any(label[k:k+z_patch, l:l+y_patch, m:m+x_patch]):
                        nb_fg += 1
                    else:
                        nb_bg += 1

        # allocate training array
        x_fg = np.empty((nb_fg, z_patch, y_patch, x_patch, channels), dtype=img.dtype)
        x_bg = np.empty((nb_bg, z_patch, y_patch, x_patch, channels), dtype=img.dtype)
        y_fg = np.empty((nb_fg, z_patch, y_patch, x_patch), dtype=label.dtype)
        y_bg = np.empty((nb_bg, z_patch, y_patch, x_patch), dtype=label.dtype)

        # create training set
        nb_fg, nb_bg = 0, 0
        for k in range(0, zsh-z_patch+1, stride_size):
            for l in range(0, ysh-y_patch+1, stride_size):
                for m in range(0, xsh-x_patch+1, stride_size):
                    if np.any(label[k:k+z_patch, l:l+y_patch, m:m+x_patch]):
                        x_fg[nb_fg,:,:,:,0] = img[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                        if channels == 2:
                            x_fg[nb_fg,:,:,:,1] = position[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                        y_fg[nb_fg] = label[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                        nb_fg += 1
                    else:
                        x_bg[nb_bg,:,:,:,0] = img[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                        if channels == 2:
                            x_bg[nb_bg,:,:,:,1] = position[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                        y_bg[nb_bg] = label[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                        nb_bg += 1

        # shuffel foreground
        arr = np.arange(nb_fg)
        np.random.shuffle(arr)
        tmp = np.copy(x_fg)
        for k in range(nb_fg):
            tmp[k] = x_fg[arr[k]]
        x_fg = np.copy(tmp)
        tmp = np.copy(y_fg)
        for k in range(nb_fg):
            tmp[k] = y_fg[arr[k]]
        y_fg = np.copy(tmp)

        # shuffel background
        arr = np.arange(nb_bg)
        np.random.shuffle(arr)
        tmp = np.copy(x_bg)
        for k in range(nb_bg):
            tmp[k] = x_bg[arr[k]]
        x_bg = np.copy(tmp)
        tmp = np.copy(y_bg)
        for k in range(nb_bg):
            tmp[k] = y_bg[arr[k]]
        y_bg = np.copy(tmp)

        # number of training samples
        nb = min(nb_fg, nb_bg)

        # balance data
        x_train = np.append(x_fg[:nb], x_bg[:nb], axis=0)
        y_train = np.append(y_fg[:nb], y_bg[:nb], axis=0)

    else:

        # img shape
        zsh, ysh, xsh = img.shape

        # get number of patches
        nb = 0
        for k in range(0, zsh-z_patch+1, stride_size):
            for l in range(0, ysh-y_patch+1, stride_size):
                for m in range(0, xsh-x_patch+1, stride_size):
                    nb += 1

        # allocate training array
        x_train = np.empty((nb, z_patch, y_patch, x_patch, channels), dtype=img.dtype)
        y_train = np.empty((nb, z_patch, y_patch, x_patch), dtype=label.dtype)

        # create training set
        nb = 0
        for k in range(0, zsh-z_patch+1, stride_size):
            for l in range(0, ysh-y_patch+1, stride_size):
                for m in range(0, xsh-x_patch+1, stride_size):
                    x_train[nb,:,:,:,0] = img[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                    if channels == 2:
                        x_train[nb,:,:,:,1] = position[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                    y_train[nb] = label[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                    nb += 1

    return x_train, y_train

def train_semantic_segmentaion(path_to_model, z_patch, y_patch, x_patch, allLabels, epochs, batch_size, \
                        gpus, x_train, y_train, channels, validation_split):

    # number of labels
    nb_labels = len(allLabels)

    # input shape
    input_shape = (z_patch, y_patch, x_patch, channels)

    # training data
    x_train = x_train.astype(np.float32)
    y_train = y_train.astype(np.int32)

    # make arrays divisible by batch_size
    rest = x_train.shape[0] % batch_size
    rest = x_train.shape[0] - rest
    x_train = x_train[:rest]
    y_train = y_train[:rest]

    # reshape arrays
    nsh, zsh, ysh, xsh, _ = x_train.shape
    x_train = x_train.reshape(nsh, zsh, ysh, xsh, channels)
    y_train = y_train.reshape(nsh, zsh, ysh, xsh, 1)

    # create one-hot vector
    y_train = to_categorical(y_train, num_classes=nb_labels)

    # make model
    model = make_unet(input_shape, nb_labels)

    # train model
    if gpus > 1:
        parallel_model = multi_gpu_model(model, gpus=gpus)
        sgd = SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)
        parallel_model.compile(loss='categorical_crossentropy',
                      optimizer=sgd,
                      metrics=['accuracy'])
        parallel_model.fit(x_train, y_train,
                  epochs=epochs,
                  batch_size=batch_size,
                  validation_split=validation_split)
    else:
        sgd = SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)
        model.compile(loss='categorical_crossentropy',
                      optimizer=sgd,
                      metrics=['accuracy'])
        model.fit(x_train, y_train,
                  epochs=epochs,
                  batch_size=batch_size,
                  validation_data=validation_split)

    # save model
    model.save(str(path_to_model))

def load_prediction_data(path_to_img, channels, x_scale, y_scale, z_scale, \
                        path_to_model, normalize, mu, sig):

    # read image data
    img, _ = load_data(path_to_img, 'first_queue')
    if img is None:
        InputError.message = "Invalid image data '%s.'" %(os.path.basename(path_to_img))
        raise InputError()
    z_shape, y_shape, x_shape = img.shape
    img = img.astype(np.float32)
    img = img_resize(img, z_scale, y_scale, x_scale)
    img -= np.amin(img)
    img /= np.amax(img)
    if normalize:
        mu_tmp, sig_tmp = np.mean(img), np.std(img)
        img = (img - mu_tmp) / sig_tmp
        img = img * sig + mu
        img[img<0] = 0
        img[img>1] = 1

    # compute position data
    position = None
    if channels == 2:
        position = np.empty((z_scale, y_scale, x_scale), dtype=np.float32)
        position = compute_position(position, z_scale, y_scale, x_scale)
        position = np.sqrt(position)
        position /= np.amax(position)

    return img, position, z_shape, y_shape, x_shape

def predict_semantic_segmentation(img, position, path_to_model, path_to_final, z_patch, y_patch, x_patch, \
                z_shape, y_shape, x_shape, compress, header, channels, stride_size, allLabels, batch_size):

    # img shape
    zsh, ysh, xsh = img.shape

    # get number of 3D-patches
    nb = 0
    for k in range(0, zsh-z_patch+1, stride_size):
        for l in range(0, ysh-y_patch+1, stride_size):
            for m in range(0, xsh-x_patch+1, stride_size):
                nb += 1

    # allocate memory
    x_test = np.empty((nb, z_patch, y_patch, x_patch, channels), dtype=img.dtype)

    # create testing set
    nb = 0
    for k in range(0, zsh-z_patch+1, stride_size):
        for l in range(0, ysh-y_patch+1, stride_size):
            for m in range(0, xsh-x_patch+1, stride_size):
                x_test[nb,:,:,:,0] = img[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                if channels == 2:
                    x_test[nb,:,:,:,1] = position[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                nb += 1

    # reshape testing set
    x_test = x_test.reshape(nb, z_patch, y_patch, x_patch, channels)

    # load model
    model = load_model(str(path_to_model))

    # predict
    tmp = model.predict(x_test, batch_size=batch_size, verbose=0, steps=None)

    # create final
    final = np.zeros((zsh, ysh, xsh, tmp.shape[4]), dtype=np.float32)
    nb = 0
    for k in range(0, zsh-z_patch+1, stride_size):
        for l in range(0, ysh-y_patch+1, stride_size):
            for m in range(0, xsh-x_patch+1, stride_size):
                final[k:k+z_patch, l:l+y_patch, m:m+x_patch] += tmp[nb]
                nb += 1

    # get final
    out = np.argmax(final, axis=3)
    out = out.astype(np.uint8)

    # rescale final to input size
    np_unique = np.unique(out)
    label = np.zeros((z_shape, y_shape, x_shape), dtype=out.dtype)
    for k in np_unique:
        tmp = np.zeros_like(out)
        tmp[out==k] = 1
        tmp = img_resize(tmp, z_shape, y_shape, x_shape)
        label[tmp==1] = k

    # save final
    label = label.astype(np.uint8)
    label = get_labels(label, allLabels)
    if header is not None:
        header = adjust_header(header, label)
    save_data(path_to_final, label, header=header, compress=compress)

def predict_pre_final(img, path_to_model, x_scale, y_scale, z_scale, z_patch, y_patch, x_patch, \
                      normalize, mu, sig, channels, stride_size, batch_size):

    # img shape
    z_shape, y_shape, x_shape = img.shape

    # load position data
    if channels == 2:
        position = np.empty((z_scale, y_scale, x_scale), dtype=np.float32)
        position = compute_position(position, z_scale, y_scale, x_scale)
        position = np.sqrt(position)
        position /= np.amax(position)

    # resize img data
    img = img.astype(np.float32)
    img = img_resize(img, z_scale, y_scale, x_scale)
    img -= np.amin(img)
    img /= np.amax(img)
    if normalize:
        mu_tmp, sig_tmp = np.mean(img), np.std(img)
        img = (img - mu_tmp) / sig_tmp
        img = img * sig + mu
        img[img<0] = 0
        img[img>1] = 1

    # img shape
    zsh, ysh, xsh = img.shape

    # get number of 3D-patches
    nb = 0
    for k in range(0, zsh-z_patch+1, stride_size):
        for l in range(0, ysh-y_patch+1, stride_size):
            for m in range(0, xsh-x_patch+1, stride_size):
                nb += 1

    # allocate memory
    x_test = np.empty((nb, z_patch, y_patch, x_patch, channels), dtype=img.dtype)

    # create testing set
    nb = 0
    for k in range(0, zsh-z_patch+1, stride_size):
        for l in range(0, ysh-y_patch+1, stride_size):
            for m in range(0, xsh-x_patch+1, stride_size):
                x_test[nb,:,:,:,0] = img[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                if channels == 2:
                    x_test[nb,:,:,:,1] = position[k:k+z_patch, l:l+y_patch, m:m+x_patch]
                nb += 1

    # reshape testing set
    x_test = x_test.reshape(nb, z_patch, y_patch, x_patch, channels)

    # load model
    model = load_model(str(path_to_model))

    # predict
    tmp = model.predict(x_test, batch_size=batch_size, verbose=0, steps=None)

    # create final
    final = np.zeros((zsh, ysh, xsh, tmp.shape[4]), dtype=np.float32)
    nb = 0
    for k in range(0, zsh-z_patch+1, stride_size):
        for l in range(0, ysh-y_patch+1, stride_size):
            for m in range(0, xsh-x_patch+1, stride_size):
                final[k:k+z_patch, l:l+y_patch, m:m+x_patch] += tmp[nb]
                nb += 1

    # get final
    out = np.argmax(final, axis=3)
    out = out.astype(np.uint8)

    # rescale final to input size
    np_unique = np.unique(out)
    label = np.zeros((z_shape, y_shape, x_shape), dtype=out.dtype)
    for k in np_unique:
        tmp = np.zeros_like(out)
        tmp[out==k] = 1
        tmp = img_resize(tmp, z_shape, y_shape, x_shape)
        label[tmp==1] = k

    return label

#=====================
# refine
#=====================

def load_training_data_refine(path_to_model, x_scale, y_scale, z_scale, patch_size, z_patch, y_patch, x_patch, normalize, \
                    img_list, label_list, channels, stride_size, allLabels, mu, sig, batch_size):

    # get filenames
    img_names, label_names = [], []
    for img_name, label_name in zip(img_list, label_list):
        if img_name[-4:] == '.tar' and label_name[-4:] == '.tar':
            for data_type in ['.am','.tif','.tiff','.hdr','.mhd','.mha','.nrrd','.nii','.nii.gz']:
                tmp_img_names = glob(img_name[:-4]+'/*/*'+data_type)+glob(img_name[:-4]+'/*'+data_type)
                tmp_label_names = glob(label_name[:-4]+'/*/*'+data_type)+glob(label_name[:-4]+'/*'+data_type)
                tmp_img_names = sorted(tmp_img_names)
                tmp_label_names = sorted(tmp_label_names)
                img_names.extend(tmp_img_names)
                label_names.extend(tmp_label_names)
        else:
            img_names.append(img_name)
            label_names.append(label_name)

    # predict pre-final
    final = []
    for name in img_names:
        a, _ = load_data(name, 'first_queue')
        if a is None:
            InputError.message = "Invalid image data '%s.'" %(os.path.basename(name))
            raise InputError()
        a = predict_pre_final(a, path_to_model, x_scale, y_scale, z_scale, z_patch, y_patch, x_patch, \
                              normalize, mu, sig, channels, stride_size, batch_size)
        a = a.astype(np.float32)
        a /= len(allLabels) - 1
        #a = make_axis_divisible_by_patch_size(a, patch_size)
        final.append(a)

    # load img data
    img = []
    for name in img_names:
        a, _ = load_data(name, 'first_queue')
        a = a.astype(np.float32)
        a -= np.amin(a)
        a /= np.amax(a)
        if normalize:
            mu_tmp, sig_tmp = np.mean(a), np.std(a)
            a = (a - mu_tmp) / sig_tmp
            a = a * sig + mu
            a[a<0] = 0
            a[a>1] = 1
        #a = make_axis_divisible_by_patch_size(a, patch_size)
        img.append(a)

    # load label data
    label = []
    for name in label_names:
        a, _ = load_data(name, 'first_queue')
        if a is None:
            InputError.message = "Invalid label data '%s.'" %(os.path.basename(name))
            raise InputError()
        #a = make_axis_divisible_by_patch_size(a, patch_size)
        label.append(a)

    # labels must be in ascending order
    for i in range(len(label)):
        for k, l in enumerate(allLabels):
            label[i][label[i]==l] = k

    return img, label, final

def config_training_data_refine(img, label, final, patch_size, stride_size):

    # get number of patches
    nb = 0
    for i in range(len(img)):
        zsh, ysh, xsh = img[i].shape
        for k in range(0, zsh-patch_size+1, stride_size):
            for l in range(0, ysh-patch_size+1, stride_size):
                for m in range(0, xsh-patch_size+1, stride_size):
                    tmp = np.copy(final[i][k:k+patch_size, l:l+patch_size, m:m+patch_size])
                    #if 0.1 * patch_size**3 < np.sum(tmp > 0) < 0.9 * patch_size**3:
                    if np.any(tmp[1:]!=tmp[0,0,0]):
                        nb += 1

    # create training data
    x_train = np.empty((nb, patch_size, patch_size, patch_size, 2), dtype=img[0].dtype)
    y_train = np.empty((nb, patch_size, patch_size, patch_size), dtype=label[0].dtype)

    nb = 0
    for i in range(len(img)):
        zsh, ysh, xsh = img[i].shape
        for k in range(0, zsh-patch_size+1, stride_size):
            for l in range(0, ysh-patch_size+1, stride_size):
                for m in range(0, xsh-patch_size+1, stride_size):
                    tmp = np.copy(final[i][k:k+patch_size, l:l+patch_size, m:m+patch_size])
                    #if 0.1 * patch_size**3 < np.sum(tmp > 0) < 0.9 * patch_size**3:
                    if np.any(tmp[1:]!=tmp[0,0,0]):
                        x_train[nb,:,:,:,0] = img[i][k:k+patch_size, l:l+patch_size, m:m+patch_size]
                        x_train[nb,:,:,:,1] = tmp
                        y_train[nb] = label[i][k:k+patch_size, l:l+patch_size, m:m+patch_size]
                        nb += 1

    return x_train, y_train

def train_semantic_segmentaion_refine(img, label, final, path_to_model, patch_size, \
                    epochs, batch_size, gpus, allLabels, validation_split, stride_size):

    # number of labels
    nb_labels = len(allLabels)

    # load training
    x_train, y_train = config_training_data_refine(img, label, final, patch_size, stride_size)
    x_train = x_train.astype(np.float32)
    y_train = y_train.astype(np.int32)

    # make arrays divisible by batch_size
    rest = x_train.shape[0] % batch_size
    rest = x_train.shape[0] - rest
    x_train = x_train[:rest]
    y_train = y_train[:rest]

    # reshape arrays
    nsh, zsh, ysh, xsh, _ = x_train.shape
    x_train = x_train.reshape(nsh, zsh, ysh, xsh, 2)
    y_train = y_train.reshape(nsh, zsh, ysh, xsh, 1)

    # create one-hot vector
    y_train = to_categorical(y_train, num_classes=nb_labels)

    # input shape
    input_shape = (patch_size, patch_size, patch_size, 2)

    # make model
    model = make_unet(input_shape, nb_labels)

    # train model
    if gpus > 1:
        parallel_model = multi_gpu_model(model, gpus=gpus)
        sgd = SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)
        parallel_model.compile(loss='categorical_crossentropy',
                      optimizer=sgd,
                      metrics=['accuracy'])
        parallel_model.fit(x_train, y_train,
                  epochs=epochs,
                  batch_size=batch_size,
                  validation_split=validation_split)
    else:
        sgd = SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)
        model.compile(loss='categorical_crossentropy',
                      optimizer=sgd,
                      metrics=['accuracy'])
        model.fit(x_train, y_train,
                  epochs=epochs,
                  batch_size=batch_size,
                  validation_split=validation_split)

    # save model
    model.save(str(path_to_model))

def load_refine_data(path_to_img, path_to_final, path_to_model, patch_size, normalize, allLabels, mu, sig):

    # read image data
    img, _ = load_data(path_to_img, 'first_queue')
    if img is None:
        InputError.message = "Invalid image data '%s.'" %(os.path.basename(path_to_img))
        raise InputError()
    z_shape, y_shape, x_shape = img.shape
    img = img.astype(np.float32)
    img -= np.amin(img)
    img /= np.amax(img)
    if normalize:
        mu_tmp, sig_tmp = np.mean(img), np.std(img)
        img = (img - mu_tmp) / sig_tmp
        img = img * sig + mu
        img[img<0] = 0
        img[img>1] = 1
    #img = make_axis_divisible_by_patch_size(img, patch_size)

    # load label data
    label, _ = load_data(path_to_final, 'first_queue')
    if label is None:
        InputError.message = "Invalid label data '%s.'" %(os.path.basename(path_to_final))
        raise InputError()
    #label = make_axis_divisible_by_patch_size(label, patch_size)

    # labels must be in ascending order
    for k, l in enumerate(allLabels):
        label[label==l] = k

    # load final data and scale to [0,1]
    final = np.copy(label)
    final = final.astype(np.float32)
    final /= len(allLabels) - 1

    return img, label, final, z_shape, y_shape, x_shape

def refine_semantic_segmentation(path_to_img, path_to_final, path_to_model, patch_size,\
                                 compress, header, normalize, stride_size, allLabels, \
                                 mu, sig, batch_size):

    # load refine data
    img, label, final, z_shape, y_shape, x_shape = load_refine_data(path_to_img, path_to_final,\
                                             path_to_model, patch_size, normalize, allLabels, mu, sig)

    # get number of 3D-patches
    nb = 0
    zsh, ysh, xsh = img.shape
    for k in range(0, zsh-patch_size+1, stride_size):
        for l in range(0, ysh-patch_size+1, stride_size):
            for m in range(0, xsh-patch_size+1, stride_size):
                tmp = label[k:k+patch_size, l:l+patch_size, m:m+patch_size]
                #if 0.1 * patch_size**3 < np.sum(tmp > 0) < 0.9 * patch_size**3:
                if np.any(tmp[1:]!=tmp[0,0,0]):
                    nb += 1

    # create prediction set
    x_test = np.empty((nb, patch_size, patch_size, patch_size, 2), dtype=img.dtype)
    nb = 0
    zsh, ysh, xsh = img.shape
    for k in range(0, zsh-patch_size+1, stride_size):
        for l in range(0, ysh-patch_size+1, stride_size):
            for m in range(0, xsh-patch_size+1, stride_size):
                tmp = label[k:k+patch_size, l:l+patch_size, m:m+patch_size]
                #if 0.1 * patch_size**3 < np.sum(tmp > 0) < 0.9 * patch_size**3:
                if np.any(tmp[1:]!=tmp[0,0,0]):
                    x_test[nb,:,:,:,0] = img[k:k+patch_size, l:l+patch_size, m:m+patch_size]
                    x_test[nb,:,:,:,1] = final[k:k+patch_size, l:l+patch_size, m:m+patch_size]
                    nb += 1

    # reshape prediction data
    x_test = x_test.reshape(nb, patch_size, patch_size, patch_size, 2)

    # load model
    model = load_model(str(path_to_model))

    # predict
    prob = model.predict(x_test, batch_size=batch_size, verbose=0, steps=None)

    # create final
    nb = 0
    zsh, ysh, xsh = img.shape
    final = np.zeros((zsh, ysh, xsh, prob.shape[4]), dtype=np.float32)
    for k in range(0, zsh-patch_size+1, stride_size):
        for l in range(0, ysh-patch_size+1, stride_size):
            for m in range(0, xsh-patch_size+1, stride_size):
                tmp = label[k:k+patch_size, l:l+patch_size, m:m+patch_size]
                #if 0.1 * patch_size**3 < np.sum(tmp > 0) < 0.9 * patch_size**3:
                if np.any(tmp[1:]!=tmp[0,0,0]):
                    final[k:k+patch_size, l:l+patch_size, m:m+patch_size] += prob[nb]
                    nb += 1

    final = np.argmax(final, axis=3)
    final = final.astype(np.uint8)

    out = np.copy(label)
    for k in range(0, zsh-patch_size+1, stride_size):
        for l in range(0, ysh-patch_size+1, stride_size):
            for m in range(0, xsh-patch_size+1, stride_size):
                tmp = label[k:k+patch_size, l:l+patch_size, m:m+patch_size]
                #if 0.1 * patch_size**3 < np.sum(tmp > 0) < 0.9 * patch_size**3:
                if np.any(tmp[1:]!=tmp[0,0,0]):
                    out[k:k+patch_size, l:l+patch_size, m:m+patch_size] = final[k:k+patch_size, l:l+patch_size, m:m+patch_size]

    # save final
    out = out.astype(np.uint8)
    out = get_labels(out, allLabels)
    out = out[:z_shape, :y_shape, :x_shape]
    if header is not None:
        header = adjust_header(header, out)
    save_data(path_to_final, out, header=header, compress=compress)
