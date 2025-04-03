import os
import math

from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

import crossfiledialog as cfd
import platformdirs

from PIL import Image, ImageChops

from morphsuit import morph, gimp, ui


app_config = ui.AppConfig('gato')

project_dir = app_config.memory_select(cfd.choose_folder)

project = gimp.GimpProject(project_dir, gimp_file='exports.xcf')
#

outdir = os.path.join(project.output_dir, 'dyno')

scale_factor = 16/100

for name, layer in project.layers.items():

    if 'eye' in name:
        scale_factor = 16/100
    elif 'bean' in name:
        scale_factor = 16/100
    elif 'battery' in name:
        scale_factor = 16/100
    elif 'led' in name:
        scale_factor = 16/50
    elif 'pin' in name:
        scale_factor = 16/50
    elif 'tack' in name:
        scale_factor = 16/100
    elif 'bnc' in name:
        scale_factor = 16/100
    else:
        print(f'No {name}')
        continue


    image = layer.image
    w,h= image.size
    image = image.resize((round(w*scale_factor), round(h*scale_factor)))
    image.save(os.path.join(outdir, f'{name}.png'))


