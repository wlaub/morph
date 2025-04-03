import os
import math

from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

import crossfiledialog as cfd
import platformdirs

from PIL import Image, ImageChops

from morphsuit import morph, gimp, ui

base_name = '320.lco.b'
configs = {
'336.lco': {
    'mid_offset': -4,
    'step_rate': 2,
    },
'320.lco.b': {
    'mid_offset': 0,
    'step_rate': 2,
    },
'336.lcue': {
    'mid_offset': 0,
    'step_rate': 2,
    },


}

mid_offset = configs[base_name]['mid_offset']
step_rate = configs[base_name]['step_rate']






app_config = ui.AppConfig('gato')

#project_dir = app_config.memory_select(cfd.choose_folder)
#print(project_dir)
project_dir = "/media/wlaub/Archive/WednesdayMachine/CelesteAssets/magbe/misc_deco/torn_edges_1"

outdir = os.path.join(project_dir, 'outputs/tears')


infile = os.path.join(project_dir, f'{base_name}.png')

image = Image.open(infile)

w,h = image.size

print(w,h)
#top = image.crop([0, 0, w, h/2-mid_offset])
#bot = image.crop([0, h/2-mid_offset, w, h])
top = image.copy()
bot = image.copy()

midline = round(h/2-mid_offset)
print(midline)

top.paste((0,0,0,255), (0,midline,w,h))
bot.paste((0,0,0,255), (0,0,w,midline))

frames = []

shift = 0
while True:

    print(shift)
#    shift = 14

    top_mask = Image.new('RGBA', (w,h), (0,0,0,0))
    bot_mask = Image.new('RGBA', (w,h), (0,0,0,0))

    top_mask.paste(top, (0,shift))
    bot_mask.paste(bot, (0,-shift))

    out_image = ImageChops.multiply(top_mask, bot_mask)
#    top_mask.show()
#    bot_mask.show()
#    out_image.show()

    frames.append(out_image)

    if not out_image.getbbox():
        break

    shift += step_rate
#    if shift > h/2:
#        break


for idx, frame in enumerate(frames[::-1]):
    name = f'{base_name}{idx:02}.png'
    outpath = os.path.join(outdir, name)

    frame.save(outpath)

