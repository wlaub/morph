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

project = gimp.GimpProject(project_dir, segs_filename='segs.json')
#project.init_sprites('hazard')

#Build the frames

project.expand_layers('masks', 2, pad_bounds = False)
#Build the entire frame
color = (0,0,0,0)
if False:
    color= (255,255,255,255)

composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')


for mask_name in project.groups['masks']:
    color_name = mask_name.split('_')[0]

    try:
        a = project.mask_layers(color_name, mask_name)
        project.paste(composed_frame, a)
    except KeyError:
        print(f'No color mask for {color_name}')

project.paste(composed_frame, 'lines')
#project.paste_group(composed_frame, 'overlays')

#Chop it up into individual parts
project.extract_sprite_frames(composed_frame)

project.export_sprites('raw_outputs', sprite_scale=52/8)
project.export_sprites('scale_outputs')



project = gimp.GimpProject(project_dir, segs_filename='segs.json')
#project.init_sprites('hazard')

exit()

#kevin stuff
#Build the frames

project.expand_layers('masks', 4, pad_bounds = False)
#Build the entire frame
color = (0,0,0,0)
if False:
    color= (255,255,255,255)

composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')


for mask_name in project.groups['masks']:
    color_name = mask_name.split('_')[0]

    if color_name == 'blue':
        color_name = 'oj1'
    elif color_name == 'eye0':
        color_name = 'red'
    elif color_name == 'brown':
        color_name = 'yel1'
    elif color_name == 'face':
        color_name = 'yel1'
    elif color_name == 'derek':
        color_name = 'yel0'
    elif color_name == 'gray':
        color_name = 'pk6'

    try:
        a = project.mask_layers(color_name, mask_name)
        project.paste(composed_frame, a)
    except KeyError:
        print(f'No color mask for {color_name}')

project.paste(composed_frame, 'lines')
#project.paste_group(composed_frame, 'overlays')

#Chop it up into individual parts
project.extract_sprite_frames(composed_frame)

project.export_sprites('raw_derek', sprite_scale=52/8)


