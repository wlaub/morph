import os
import math
import random

from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

import crossfiledialog as cfd
import platformdirs

from PIL import Image, ImageChops

from morphsuit import morph, gimp, ui


app_config = ui.AppConfig('gato')

#project_dir = app_config.memory_select(cfd.choose_folder)
project_dir = app_config.config.get('current_project')


project = gimp.GimpProject(project_dir, segs_filename='segs.json')
#project.init_sprites('hazard')

pixel_size, tile_size = project._get_export_sizes(None, None)
grid_size = pixel_size/tile_size

mirrors_offset = [grid_size*11,0]
shards_offset = [0,grid_size*3]

mirror_masks = []
mirror_colors = []
for color in project.groups['colors']:
    try:
        int(color)
        mirror_masks.append(color)
    except ValueError:
        mirror_colors.append(color)

# Get main mirror masks
def get_mirror_masks():
    mask_groups = defaultdict(list)
    c_buffer = list(project.label_map['mirror000'])
    idx = 0
    while len(c_buffer) > 0:
        c_idx = random.randint(0,len(c_buffer)-1)
        val = c_buffer.pop(c_idx)

        mask_groups[mirror_masks[idx]].append(val)

        idx+=1
        idx %= len(mirror_masks)

    mirror_sprites = {}
    for k,v in mask_groups.items():
        sprite = gimp.SpriteMask(v, k, project.size, ref_points = None, offset=mirrors_offset)
        mirror_sprites[k]=sprite
    #mirror_sprites['0'].image.show()

    mirror_mask_masks = {}
    mirror_mask_mask = Image.new('RGBA', project.size)
    mirror_mask_mask.paste(project.layers['sprites'].image, [round(x) for x in mirrors_offset])

    for k, v in mirror_sprites.items():
       mirror_mask_masks[k] = project.mask_layers(mirror_mask_mask, v.image)

    return mirror_mask_masks

# Get shard mirror masks

shard_mirror_sprites = {}
for k,v in project.label_map.items():
    if k == 'mirror000': continue
    shard_mirror_sprites[k] = gimp.SpriteMask(v, k, project.size, ref_points = None, offset=shards_offset)

shard_mirror_mask = Image.new('RGBA', project.size)
piece = project.layers['sprites'].image.crop([0, 0,project.size[0], grid_size*6])
shard_mirror_mask.paste(piece, [round(x) for x in shards_offset])


shapes = {
(1,1):5,

(1,2):5,
(2,2):7,

(1,3):4,
(2,3):7,
(3,3):7,

(1,4):3,
(2,4):4,
(3,4):5,
(4,4):7,

(1,5):3,
(2,5):3,
(3,5):4,
(4,5):5,
(5,5):7,

}

frames = {}
for shape, count in shapes.items():
    #main mirrors frame
    print(f'doing {shape}')
    mirror_mask_masks = get_mirror_masks()
    for mirror_color in mirror_colors:
        color = (0,0,0,0)
        if False:
            color= (255,255,255,255)

        composed_frame = project.make_new_image(color=color)

        #The mirrors
        a = project.mask_layers(mirror_color, 'sprites')
        project.paste(composed_frame, a)

        for mirror_mask_color, mirror_mask in mirror_mask_masks.items():
            a = project.mask_layers(mirror_mask_color, mirror_mask)
            project.paste(composed_frame, a)

        frames[(shape, mirror_color)] = composed_frame

circles_raw = {
2: """
   1  -0.207106781186547524400844362105  -0.207106781186547524400844362105
   2   0.207106781186547524400844362105   0.207106781186547524400844362105
""",
3: """
   1  -0.245666904969750182245255239572  -0.245666904969750182245255239572
   2   0.245666904969750182245255239572  -0.114014407382354328773728782162
   3  -0.114014407382354328773728782162   0.245666904969750182245255239572
""",
4: """
   1  -0.250000000000000000000000000000  -0.250000000000000000000000000000
   2   0.250000000000000000000000000000  -0.250000000000000000000000000000
   3  -0.250000000000000000000000000000   0.250000000000000000000000000000
   4   0.250000000000000000000000000000   0.250000000000000000000000000000
""",
5: """
   1  -0.292893218813452475599155637895  -0.292893218813452475599155637895
   2   0.292893218813452475599155637895  -0.292893218813452475599155637895
   3   0.000000000000000000000000000000   0.000000000000000000000000000000
   4  -0.292893218813452475599155637895   0.292893218813452475599155637895
   5   0.292893218813452475599155637895   0.292893218813452475599155637895
""",
6: """
   1  -0.312319398852523135680101573808  -0.312319398852523135680101573808
   2   0.312319398852523135680101573808  -0.312319398852523135680101573808
   3   0.000000000000000000000000000000  -0.104106466284174378560033857936
   4  -0.312319398852523135680101573808   0.104106466284174378560033857936
   5   0.312319398852523135680101573808   0.104106466284174378560033857936
   6   0.000000000000000000000000000000   0.312319398852523135680101573808
""",
7: """
   1  -0.325542369812990561040572795501  -0.325542369812990561040572795501
   2   0.023372890561028316878281613499  -0.325542369812990561040572795500
   3   0.325542369812990561040572795500  -0.151084739625981122081145591001
   4  -0.325542369812990561040572795500   0.023372890561028316878281613499
   5   0.023372890561028316878281613499   0.023372890561028316878281613499
   6   0.300000000000000000000000000000   0.300000000000000000000000000000
   7  -0.151084739625981122081145591001   0.325542369812990561040572795500
""",
}

circles = {}
for k, raw in circles_raw.items():
    lines = raw.strip().split('\n')
    circles[k] = points = []
    for line in lines:
        parts = line.split()
        point = [float(x) for x in parts[1:]]
        points.append(point)

    w = max([x[0] for x in points])-min(x[0]for x in points)
    h = max([x[1] for x in points])-min(x[1]for x in points)
    for point in points:
        point[0]/=w
        point[1]/=h


W = 9
H = 31
dx, dy = project.get_grid_offset()
left = dx + 2*grid_size
top = dy+9*grid_size
mleft = left + mirrors_offset[0]
mtop = top + mirrors_offset[1]


for (shape, mirror_color), frame in frames.items():
    w,h = shape

    l = left
    t = top

    points = circles[shapes[shape]]

    output_dir = os.path.join(project.output_dir, f'{mirror_color}/')
    os.makedirs(output_dir, exist_ok = True)
    mirror_output_dir = os.path.join(project.output_dir, f'{mirror_color}/mirror/')
    os.makedirs(mirror_output_dir, exist_ok = True)

    print(f'doing {shape}')
    for idx, point in enumerate(points):
        x,y = point
        #rotate the points each time they're used
        point[0] = -y
        point[1] = x

        sx = int((W-w-1)*x+(W-w-1)/2)
        sy = int((H-h-1)*y+(H-h-1)/2)
#        print(sx, sy, sx+w, sy+h)

        l = left+sx*grid_size
        t = top+sx*grid_size

        filename = f'{w}.{h}.{idx:02}..png'

        transpose = random.choice([Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM, Image.Transpose.ROTATE_180])

        image = frame.crop([l, t, l+grid_size*w, t+grid_size*h])
        image = image.resize((w*8, h*8))
        image = image.transpose(transpose)
        image.save(os.path.join(output_dir, filename))

        l+= mirrors_offset[0]
        t+= mirrors_offset[1]
        image = frame.crop([l, t, l+grid_size*w, t+grid_size*h])
        image = image.resize((w*8, h*8))
        image = image.transpose(transpose)
        image.save(os.path.join(mirror_output_dir, filename))


#shards
frames = {}
for mirror_mask in mirror_masks:
    #main mirrors frame
    print(f'doing {mirror_mask}')
    for mirror_color in mirror_colors:
        color = (0,0,0,0)
        if False:
            color= (255,255,255,255)

        composed_frame = project.make_new_image(color=color)

        #The mirrors
        a = project.mask_layers(mirror_color, 'sprites')
        project.paste(composed_frame, a)

        a = project.mask_layers(mirror_mask, shard_mirror_mask)
        project.paste(composed_frame, a)

        frames[(mirror_color, mirror_mask)] = composed_frame
#    composed_frame.show()

dx, dy = project.get_grid_offset()
left = dx + 2.5*grid_size-grid_size*1.5/8
top = dy+2.5*grid_size

for (mirror_color, mirror_mask), frame in frames.items():

    output_dir = os.path.join(project.output_dir, f'{mirror_color}/break/')
    os.makedirs(output_dir, exist_ok = True)
    mirror_output_dir = os.path.join(project.output_dir, f'{mirror_color}/break/mirror/')
    os.makedirs(mirror_output_dir, exist_ok = True)

    for idx in range(7):
        l = left + idx*grid_size*3
        t = top

        filename = f'{w}.{h}.{mirror_mask}.{idx:02}..png'

        transpose = random.choice([Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM, Image.Transpose.ROTATE_180])

        image = frame.crop([l, t, l+grid_size*2, t+grid_size*2])
        image = image.resize((16,16))
        image = image.transpose(transpose)
        image.save(os.path.join(output_dir, filename))

        l+= shards_offset[0]
        t+= shards_offset[1]
        image = frame.crop([l, t, l+grid_size*2, t+grid_size*2])
        image = image.resize((16,16))
        image = image.transpose(transpose)
        image.save(os.path.join(mirror_output_dir, filename))




#Build the frames
exit()
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


