from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

import crossfiledialog as cfd
import platformdirs

from PIL import Image, ImageChops

from morphsuit import morph, gimp, ui


color_sets = {
'stems': {
'stem0': '.0',
'stem1': '.2',
'stem2': '.1',
},

'gills': {
'gill0': '.0',
'gill1': '.2',
'gill2': '.1',
},

'mask0': {
'b00': '.0',
'b01': '.5',
'b02': '.2',
'b10': '.3',
'b11': '.4',
'b12': '.6',
'b21': '.1',
},
}

color_mask = 'stems'

color_suffix = color_sets[color_mask]

flat_colors = list(color_suffix.keys())


app_config = ui.AppConfig('gato')

project_dir = app_config.memory_select(cfd.choose_folder)

project = gimp.GimpProject(project_dir)
#project.init_sprites('hazard')

#Build the frames

#project.expand_layers('masks', 2, pad_bounds = False)
for flat_color in flat_colors:
    print(f'frame {flat_color}')
    #Build the entire frame
    color = (0,0,0,0)
    if False:
        color= (255,255,255,255)

    composed_frame = project.make_new_image(color=color)
#    project.paste(composed_frame, 'grid')

    a = project.mask_layers(str(flat_color), color_mask)
    project.paste(composed_frame, a)

    project.paste_group(composed_frame, 'overlays')

    project.extract_sprite_frames(composed_frame, suffix=color_suffix[flat_color])


#project.export_sprites_gif('output/gifs', gui_scale=True)
project.export_sprites(color_mask)
#project.export_sprites(color_mask+'_big', sprite_scale=2)



