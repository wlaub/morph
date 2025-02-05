from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

import crossfiledialog as cfd
import platformdirs

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

color_suffix = {
'b00': '.0',
'b01': '.5',
'b02': '.2',
'b10': '.3',
'b11': '.4',
'b12': '.6',
'b21': '.1',
}

app_config = ui.AppConfig('gato')

project_dir = app_config.memory_select(cfd.choose_folder)

project = gimp.GimpProject(project_dir)


colors = list(map(str,project.int_layers))

frame_count = len(colors)*2-2

def frame_to_color_index(frame, offset, step_offset, N):
    index = offset+int((frame+step_offset)/N)*N
    return index

def color_index_to_color(index):
    index %= frame_count
    if index < len(colors)-1:
        return index
    else:
        return frame_count - index

project.expand_layers('masks', 2, pad_bounds = False)
#Build the frames
for color_name, suffix in color_suffix.items():
    for frame in range(frame_count):
        print(f'frame {frame}')
        #Build the entire frame
        color = (0,0,0,0)
        if False:
            color= (255,255,255,255)
        composed_frame = project.make_new_image(color=color)

        for mask_name in project.groups['masks']:
            if mask_name in masks.keys():
                offset, step_offset = masks[mask_name]
                color_index = frame_to_color_index(frame, offset, step_offset, N)
                color = color_index_to_color(color_index)

                a = project.mask_layers(str(color), mask_name)
                project.paste(composed_frame, a)

        a = project.mask_layers(color_name, 'mush')
        project.paste(composed_frame, a)

        project.paste_group(composed_frame, 'overlays')
        filter_func = None
        #On non-zero frames, only extract hazard sprites
        if frame != 0:
            filter_func = lambda x: x[0] == 'h'

        #Chop it up into individual parts
        project.extract_sprite_frames(composed_frame, suffix = suffix, filter_func = filter_func)

#project.export_sprites_gif('output/gifs', gui_scale=True)
project.export_sprites('mush')






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


