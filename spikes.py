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

project = gimp.GimpProject(project_dir, segs_filename='segs_spikes.json')
#project.init_sprites('hazard')

#Build the frames

project.expand_layers('masks', 2, pad_bounds = False)
#Build the entire frame
color = (0,0,0,0)
if False:
    color= (255,255,255,255)

composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')

a = project.mask_layers('grid', 'spike')
project.paste(composed_frame, a)

project.paste_group(composed_frame, 'overlays')

project.extract_sprite_frames(composed_frame)

project.export_sprites('spikes_raw')

angle_map = {
'right': None,
'up': Image.Transpose.ROTATE_90,
'left': Image.Transpose.ROTATE_180,
'down': Image.Transpose.ROTATE_270,
}

spikes_dir = os.path.join(project_dir, 'outputs/spikes_raw')
out_dir = os.path.join(project_dir, 'outputs/spikes')
files = list(sorted(os.listdir(spikes_dir)))

os.makedirs(out_dir, exist_ok = True)
for filename in files:
    print(f'Doing {filename}')
    image = Image.open(os.path.join(spikes_dir, filename))
    base = filename.split('.')[0]
    name = base[:-2]
    idx = base[-2:]

    bbox = list(image.getbbox())

    w = bbox[3]-bbox[1]
    h = bbox[2]-bbox[0]

    if not 'wide' in name:
        bbox[0] += 2
    else:
        if h < 8:
            bbox[0] += 1
        else:
            bbox[0] += 2

    if w > 8 and not 'needle' in name:
        dw = int((w-8)/2)
        bbox[3]-=dw
        bbox[1]+=dw
        if w %2 != 0:
            bbox[3] -= 1
#        print(dw, bbox[3]-bbox[1])

    w = bbox[3]-bbox[1]
    h = bbox[2]-bbox[0]
    print(w, h)

    image = image.crop(bbox)

    for direction, angle in angle_map.items():
        output = image
        if angle is not None:
            output=image.transpose(angle)
        outname = f'{name}_{direction}{idx}.png'
        output.save(os.path.join(out_dir, outname))




