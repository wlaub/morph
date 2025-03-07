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

project = gimp.GimpProject(project_dir, segs_filename='segs_mono.json')
#project.init_sprites('hazard')

#Build the frames

project.expand_layers('masks', 2, pad_bounds = False)
#Build the entire frame
color = (0,0,0,0)
if False:
    color= (255,255,255,255)

composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')

#a = project.mask_layers('grid'u, 'spike')
#project.paste(composed_frame, a)

project.paste_group(composed_frame, 'overlays')

project.extract_sprite_frames(composed_frame, global_angle=90)

project.export_sprites('sprites')


