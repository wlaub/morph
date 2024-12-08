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

cal_dir = 'calibrations'

#cal_name = 'slot_9.txt'
cal_name = sys.argv[1]
target_dir = sys.argv[2]

src_dir = os.path.join(target_dir, 'raw_inputs')
out_dir = os.path.join(target_dir, 'inputs')

cal_file = os.path.join(cal_dir, f'{cal_name}.txt')
cal_params = io.load_metadata_txt(os.path.join(cal_file))

config_file = os.path.join(cal_dir, f'{cal_name}_config.json')
config = {}
if os.path.exists(config_file):
    with open(config_file, 'r') as fp:
        config = json.load(fp)

input_files = [x for x in os.listdir(src_dir) if x.endswith('.jpg')]
if len(input_files) == 0:
    raise RuntimeError(f'Found no inputs at {src_dir}')

os.makedirs(out_dir, exist_ok = True)

start_time = time.time()
for filename in input_files:
    print(filename)
    file_path = os.path.join(src_dir, filename)
    outname = '.'.join(filename.split('.')[:-1])+'.png'

    image = Image.open(file_path)

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
        print(f'{angle}')
        image = image.rotate(angle, expand=True)

    image = np.array(image)

    fixed = np.copy(image)
    for i in range(image.shape[-1]):

        fixed[:,:,i] = post.unwarp_image_backward(image[:,:,i], *cal_params)

    fixed = Image.fromarray(fixed)
    if 'crop' in config.keys():
        fixed = fixed.crop(config['crop'])
    if 'rotate' in config.keys():
        fixed = fixed.rotate(config['rotate'])

    fixed.save(os.path.join(out_dir, outname))

duration = time.time()-start_time
print(f'Finished in {duration:.1f} s')

