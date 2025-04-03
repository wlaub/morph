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

infile = os.path.join(project_dir, 'sheet_base.png')
outdir = os.path.join(project_dir, 'outputs/kevin')

image = Image.open(infile)

frame_map = {
'block00': (0,0),
'block01': (3,0),
'block02': (1,0),
'block03': (2,0),
'idle_face': (0,1),
'hit00': (1,1),
'hit01': (2,1),
'hit02': (3,1),
'hit_down00': (4,1),
'hit_down01': (5,1),
'hit_up00': (0,2),
'hit_up01': (1,2),
'hit_left00': (4,2),
'hit_left01': (5,2),
'hit_right00': (2,2),
'hit_right01': (3,2),
'hurt07': (1,4),
'hurt08': (2,4),
'hurt09': (3,4),
'hurt10': (4,4),
'hurt11': (5,4),
}

frame_map['hurt00'] = frame_map['hit00']
frame_map['hurt01'] = frame_map['hit01']
frame_map['hurt02'] = frame_map['hit02']
frame_map['hurt03'] = frame_map['hit_left00']
frame_map['hurt04'] = frame_map['hit_right00']
frame_map['hurt05'] = frame_map['hit_up00']
frame_map['hurt06'] = frame_map['hit_down00']
frame_map['hurt12'] = frame_map['hit00']


grid = 52

for name, (xoff, yoff) in frame_map.items():
    xoff*=6
    yoff*=6

    out_image = image.crop(((xoff+1)*grid, (yoff+1)*grid, (xoff+1+4)*grid, (yoff+1+4)*grid))

    out_image = out_image.resize((32,32))

    out_image.save(os.path.join(outdir, f'{name}.png'))

xoff = 27
yoff = 1
light_image = image.crop((xoff*grid, yoff*grid, (xoff+1)*grid, (yoff+4)*grid))
light_image = light_image.resize((8,32))

light_image.save(os.path.join(outdir, 'lit_right.png'))

lightmap = {
'lit_left': Image.Transpose.ROTATE_180,
'lit_top': Image.Transpose.ROTATE_90,
'lit_bottom': Image.Transpose.ROTATE_270,
}


for name, angle in lightmap.items():
    out_image = light_image.transpose(angle)
    out_image.save(os.path.join(outdir, f'{name}.png'))











