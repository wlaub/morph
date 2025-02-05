from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

import crossfiledialog as cfd
import platformdirs

from PIL import Image, ImageChops

from morphsuit import morph, gimp, ui

app_config = ui.AppConfig('gato')

project_dir = app_config.memory_select(cfd.choose_folder)



colors = [str(x) for x in range(21)]

frame_count = len(colors)*2-2

#0, 6, 13, 20, 27, 34
N=5 #color hold length in frames

def frame_to_color_index(frame, offset, step_offset, N):
    index = offset+int((frame+step_offset)/N)*N
    return index

def color_index_to_color(index):
    index %= frame_count
    if index < len(colors)-1:
        return index
    else:
        return frame_count - index

offset_map = [
    (20,0),
    (6,1),
    (34,0),
    (0,2),
    (13,3),
    (27,4),
]

print('doing odds')
project = gimp.GimpProject(project_dir, segs_filename = 'segs_odd.json')
project.expand_layers('masks', 1, pad_bounds = False)
for idx, (offset, step_offset) in enumerate(offset_map):
    if idx %2 == 0: continue
    color_suffix = f'.{idx}'
    mask_name = 'odd'
    angle = (idx>>1)*90

    #Build the frames
    for frame in range(frame_count):
        print(f'frame {frame}')
        #Build the entire frame
        composed_frame = project.make_new_image()
        color_index = frame_to_color_index(frame, offset, step_offset, N)
        color = color_index_to_color(color_index)

        a = project.mask_layers(str(color), mask_name)
        project.paste(composed_frame, a)

        project.paste(composed_frame, 'lines')

        project.extract_sprite_frames(composed_frame, suffix=color_suffix, global_angle = angle)

project.export_sprites('balls')

print('doing evens')
project = gimp.GimpProject(project_dir, segs_filename = 'segs_even.json')
project.expand_layers('masks', 1, pad_bounds = False)
for idx, (offset, step_offset) in enumerate(offset_map):
    if idx %2 == 1: continue
    color_suffix = f'.{idx}'
    mask_name = 'even'
    angle = (idx>>1)*90

    #Build the frames
    for frame in range(frame_count):
        print(f'frame {frame}')
        #Build the entire frame
        composed_frame = project.make_new_image()
        color_index = frame_to_color_index(frame, offset, step_offset, N)
        color = color_index_to_color(color_index)

        a = project.mask_layers(str(color), mask_name)
        project.paste(composed_frame, a)

        project.paste(composed_frame, 'lines')

        project.extract_sprite_frames(composed_frame, suffix=color_suffix, global_angle = angle)

project.export_sprites('balls')


