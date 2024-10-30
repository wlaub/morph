from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops

from morphsuit import morph, gimp

project = gimp.GimpProject('inputs.xcf', 'output')

tile_size = 39
pixel_size = 2061

colors = list(map(str,project.int_layers))

frame_count = len(colors)*2-2

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

def frame_to_color_index(frame, offset, step_offset, N):
    index = offset+int((frame+step_offset)/N)*N
    return index

def color_index_to_color(index):
    index %= frame_count
    if index < len(colors)-1:
        return index
    else:
        return frame_count - index

coverage=defaultdict(lambda: 0)
#Print the color sequences
sequences = {x: [] for x in masks.keys()}
quences = {x: [] for x in masks.keys()}
for idx in range(frame_count):
    for triset, (offset, step_offset) in masks.items():
        color_index = frame_to_color_index(idx, offset, step_offset, N)
        color = color_index_to_color(color_index)
        if len(sequences[triset]) == 0 or quences[triset][-1] != color_index:
            sequences[triset].append(color)
            quences[triset].append(color_index)
        else:
            sequences[triset].append('')
        coverage[str(color)]+=1
rows = zip(*list(sequences.values()))
print(tabulate.tabulate(rows))
for color in colors:
    print('#'*coverage[color])


#Build the frames
for frame in range(frame_count):
    print(f'frame {frame}')
    #Build the entire frame
    composed_frame = project.make_new_image()

    for mask_name, (offset, step_offset) in masks.items():
        color_index = frame_to_color_index(frame, offset, step_offset, N)
        color = color_index_to_color(color_index)

        a = project.mask_layers(str(color), mask_name)
        project.paste(composed_frame, a)

    project.paste_group(composed_frame, 'overlays')

    #Chop it up into individual parts
    project.extract_sprite_frames(composed_frame)

project.export_sprites_gif('output/gifs', pixel_size, tile_size, gui_scale=True)






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


