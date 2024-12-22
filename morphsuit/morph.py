import os
import sys
import json
import time

import numpy as np

import discorpy.losa.loadersaver as io
import discorpy.prep.preprocessing as prep
import discorpy.proc.processing as proc
import discorpy.post.postprocessing as post

from PIL import Image, ExifTags


class MorphProject():
    def __init__(self, cal_file):
        self.cal_file = cal_file
        self.cal_params = io.load_metadata_txt(os.path.join(cal_file))


    def correct_exif_orientation(self, image):
        for k,v in ExifTags.TAGS.items():
            if v == 'Orientation':
                ok = k
                break
        else:
            print('no such concept as orientation')

        exif = image._getexif()
        angles = {
            3:180, 6:270, 8:90,
            }
        angle = angles.get(exif[ok], None)
        if angle is None:
            print(f'Unknown orientation: {exif[ok]}')
        else:
            image = image.rotate(angle, expand=True)
        return image


    def lens_correct(self, image):
        image = self.correct_exif_orientation(image)

        image = np.array(image)

        fixed = np.copy(image)
        for i in range(image.shape[-1]):

            fixed[:,:,i] = post.unwarp_image_backward(image[:,:,i], *self.cal_params)

        fixed = Image.fromarray(fixed)

        return fixed



