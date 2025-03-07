import sys, os
import math
import json
from collections import defaultdict

import tabulate

import crossfiledialog as cfd
import platformdirs

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops, ImageFont, ImageDraw

from morphsuit import morph, gimp, ui

from slpp import slpp as lua

app_config = ui.AppConfig('buildrot')

if False:
    sprite_dir = app_config.memory_select(cfd.choose_folder)
    app_config.config['current_project'] = sprite_dir
    app_config.save()
else:
    sprite_dir = app_config.config.get('current_project')

infile = sys.argv[1]

with open(infile, 'r') as fp:
    data = lua.decode(fp.read())

scale=6

left = right = data[0]['x']
top = bot = data[0]['y']


trans_map = {
0: None,
90: Image.Transpose.ROTATE_270,
180: Image.Transpose.ROTATE_180,
270: Image.Transpose.ROTATE_90,
}

for decal in data:
    name = decal['texture'].split('/')[-1]
    decal['name'] = name
    path = name+'.png'
    path = os.path.join(sprite_dir, path)

    image = Image.open(path)
    if decal['scaleX'] == -1:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if decal['rotation']!=0:
        image = image.transpose(trans_map[decal['rotation']])

#    image = image.rotate(-decal['rotation'])


    decal['image'] = image

    W,H = image.size
    W/=scale
    H/=scale

    decal['x']-=W/2
    decal['y']-=H/2

    l = decal['x']
    r = l + W
    t = decal['y']
    b = t+H

    left = min(l, left)
    top = min(t, top)
    right = max(r, right)
    bot = max(b, bot)


print(left, right, top, bot)
width = math.ceil((right-left)*scale)
height = math.ceil((bot-top)*scale)

target = Image.new('RGBA', (width, height))



for decal in data:
    x = round((decal['x']-left)*scale)
    y = round((decal['y']-top)*scale)
    paste_image = decal['image']

#    mask = paste_image.getchannel('A')
#    r,g,b,mask = paste_image.split()
#    effective_image = Image.merge('RGBA', (r,g,b,mask))
    target.alpha_composite(paste_image, (x,y))

output = target.resize((round(width/(scale*8)), round(height/(scale*8))))
outname = infile.split('.')[0]+'.png'
output.save(os.path.join(sprite_dir, '../grect', outname))

target = target.copy()

font = ImageFont.truetype('UbuntuMono-R.ttf', 40)
for decal in data:
    W,H = decal['image'].size
    x = round((decal['x']-left)*scale+W/2)
    y = round((decal['y']-top)*scale+H/2)


    draw = ImageDraw.Draw(target)
    draw.text((x,y), decal['name'], (0,255,0), font=font, anchor='ms')

target.show()


