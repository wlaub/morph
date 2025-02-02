from collections import defaultdict

import tabulate

import crossfiledialog as cfd
import platformdirs

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops

from morphsuit import morph, gimp, ui

#0, 6, 13, 20, 27, 34
N=5 #color hold length in frames
masks = {
'red': (20,0),
'blue': (0,2),
'1r1b': (6,1),
'2r1b': (13,3),
'1r2b': (34,0),
'2r2b': (27,4),
'extra': (13,3),
}

color_masks = {
'mask0':'r02',
'mask1':'r11',
'mask2':'r12',
'mask3':'r21',
'mask4':'r01',
'mask5':'r00',
'mask6':'r10',
}

app_config = ui.AppConfig('gato')

project_dir = app_config.memory_select(cfd.choose_folder)

project = gimp.GimpProject(project_dir)

#project.init_sprites('sprites', 'bg')

project.expand_layers('masks', 2, pad_bounds = False)



#Build the frames
#Build the entire frame
color = (0,0,0,0)
if False:
    color= (255,255,255,255)
composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')

for mask_name in project.groups['masks']:
    if mask_name in color_masks.keys():
        color = color_masks[mask_name]
        a = project.mask_layers(str(color), mask_name)
        project.paste(composed_frame, a)
    else:
        print(f'Warning: unknown mask {mask_name}')

#project.paste(composed_frame, 'bg_haze')
#project.paste(composed_frame, 'bg_lines')
#project.paste_group(composed_frame, 'overlays')

#Chop it up into individual parts
project.extract_sprite_frames(composed_frame)

#project.export_sprites_gif('output/gifs', gui_scale=True)
project.export_sprites('sprites', sprite_scale=6/7, sprite_prefix = 'bgl')
project.export_sprites('sprites', sprite_scale=5/7, sprite_prefix = 'bgs')







"""
if False:
    sequences = {x: [] for x in masks.keys()}
    for idx in range(frame_count):
        print(f'frame {idx}')
        for triset, (offset, step_offset) in masks.items():
            color_index = frame_to_color_index(idx, offset, step_offset, N)
            if len(sequences[triset]) == 0 or sequences[triset][-1] != frame:
                sequences[triset].append(color_index)

    for triset, seq in sequences.items():
        print(f'{triset}:\t{seq} \t{len(seq)}')
"""


