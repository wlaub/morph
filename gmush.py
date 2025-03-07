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

project = gimp.GimpProject(project_dir, segs_filename='segs_gmush.json')
#project.init_sprites('hazard')

color_map = {
'.1': 'b21',
'.0': 'b02',
'.2': 'gill0',
'.3': 'gill2',
'.4': 'stem2',
}

#color_map = {
#'.1': '1',
#'.0': '0',
#'.2': '2',
#'.3': '3',
#'.4': '4',
#}

color_map = {
'.0': 'b21',
'.1': 'b10',
'.2': 'b00',
'.3': 'b11',
'.4': 'b01',
'.5': 'stem2',
'.6': 'stem0',
}



#Build the frames

#project.expand_layers('masks', 2, pad_bounds = False)i
#Build the entire frame
#for frame_color in project.groups['colors']:
#    suffix = frame_color
for suffix, frame_color in color_map.items():
    color = (0,0,0,0)
    if False:
        color= (255,255,255,255)

    composed_frame = project.make_new_image(color=color)
    #    project.paste(composed_frame, 'grid')

    a = project.mask_layers(frame_color, 'gmush2')
    project.paste(composed_frame, a)

    #project.paste_group(composed_frame, 'overlays')

    project.extract_sprite_frames(composed_frame, global_angle=90, suffix=suffix)

#project.export_sprites('gmush', sprite_scale=8/7)
project.export_sprites('gmush', sprite_scale=1/3)
#project.export_sprites('gmush', sprite_scale=80/7)

