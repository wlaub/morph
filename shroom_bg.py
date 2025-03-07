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
'h0':'b02',
'h1':'b11',
'h2':'b12',
'h3':'b21',
'h4':'b01',
'h5':'b00',
'h6':'b10',
's0':'stem0',
's1':'stem1',
's2':'stem2',
'g0':'gill0',
'g1':'gill1',
'g2':'gill2',
}

app_config = ui.AppConfig('gato')

project_dir = app_config.memory_select(cfd.choose_folder)

project = gimp.GimpProject(project_dir)

#project.init_sprites('sprites', 'bg')

#project.expand_layers('masks', 2, pad_bounds = False)

#Build the frames
#Build the entire frame
color = (0,0,0,0)
if False:
    color= (255,255,255,255)
composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')

#for mask_name, color_mask in color_masks.items():
#    image = project.layers[color_mask].image
#    project.paste(image, 'bg_haze')
project.expand_layers('masks', 1, pad_bounds = False)

for mask_name in project.groups['masks']:
    if mask_name in color_masks.keys():
        color = color_masks[mask_name]
        a = project.mask_layers(str(color), mask_name)
        project.paste(composed_frame, a)
    else:
        print(f'Warning: unknown mask {mask_name}')

project.paste(composed_frame, 'lines')
#Chop it up into individual parts
project.extract_sprite_frames(composed_frame)

#project.export_sprites_gif('output/gifs', gui_scale=True)
project.export_sprites('bgm', sprite_scale=2, sprite_prefix = 'l.')
project.export_sprites('bgm', sprite_scale=1, sprite_prefix = 's.')

exit(0)

project.sprites = {}
color = (0,0,0,0)
if False:
    color= (255,255,255,255)
composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')

for mask_name, color_mask in color_masks.items():
    image = project.layers[color_mask].image
    project.paste(image, 'bg_haze')

for mask_name in project.groups['masks']:
    if mask_name in color_masks.keys():
        color = color_masks[mask_name]
        a = project.mask_layers(str(color), mask_name)
        project.paste(composed_frame, a)
    else:
        print(f'Warning: unknown mask {mask_name}')

#Chop it up into individual parts
project.extract_sprite_frames(composed_frame)



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


