import math
import os

from collections import defaultdict

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageOps

from gimpformats.gimpXcfDocument import GimpDocument

def pil_to_cv(x):
    if x.has_transparency_data:
        return cv2.cvtColor(np.array(x), cv2.COLOR_RGBA2BGRA)
    else:
        return cv2.cvtColor(np.array(x), cv2.COLOR_RGB2BGR)

def cv_to_pil(x):
    if x.shape[2] == 3:
        return Image.fromarray(cv2.cvtColor(x, cv2.COLOR_BGR2RGB))
    elif x.shape[2] == 4:
        return Image.fromarray(cv2.cvtColor(x, cv2.COLOR_BGRA2RGBA))
    else:
        raise ValueError(f'Not enough dimensions in {x.shape}')

class WrappedLayer():
    def __init__(self, layer):
        self.layer=layer
        self.image=None

    def sub_image(self, image):
        self.image = image

    def __getattr__(self, name):
        if name == 'image' and self.image is not None:
            return self.image
        return getattr(self.layer, name)

class GimpProject():
    def __init__(self, filename, cache_dir):
        self.filename = filename
        self.cache_dir = cache_dir
        self.data = GimpDocument(filename)

        self.init_sprites()
        self.init_layers()

        self._sub_cache(loud=False)

    def init_sprites(self):
        self.sprites = {}

    @classmethod
    def _convert_number(cls, x):
        try:
            return float(x)
        except ValueError:
            return x

    @classmethod
    def _convert_list(cls, x):
        if not isinstance(x,str):
            return x
        if not ',' in x:
            return x

        parts = [y.strip() for y in x.split(',')]
        return list(map(cls._convert_number, parts))

    def init_layers(self):
        self.layers = {}
        self.groups = defaultdict(list)
        self.variables = {}

        variable_count = defaultdict(lambda: 0)

        self.int_layers = []
        active_group = None
        for layer in self.data.layers:
            if layer.isGroup:
                active_group = layer.name
                if '=' in layer.name:
                    for piece in layer.name.split('|'):
                        try:
                            var_name, var_val = [x.strip() for x in piece.split('=')]
                            var_val = self._convert_number(var_val)
                            var_val = self._convert_list(var_val)
                            if variable_count[var_name] > 0:
                                if variable_count[var_name] == 1:
                                    self.variables[var_name] = [self.variables[var_name]]
                                self.variables[var_name].append(var_val)
                            else:
                                self.variables[var_name] = var_val
                            variable_count[var_name]+= 1
                        except Exception as e:
                            print(f'Failed to process variable layer {piece}: {e}')

                continue
            self.layers[layer.name] = WrappedLayer(layer)

            try:
                self.int_layers.append(int(layer.name))
            except ValueError:
                pass

            if layer.itemPath is not None:
                if active_group is None:
                    print(f'Error: {layer.name=}, {layer.itempPath=} but no active group')
                else:
                    self.groups[active_group].append(layer.name)
            else:
                active_group = None


    @property
    def size(self):
        return self.data.width, self.data.height

    def export_layers(self, layer_group = None, loud=True):
        for layer in self.data.layers:
            if layer_group is not None and layer.name not in self.groups[layer_group]:
                continue
            name = os.path.join(self.cache_dir, f'{layer.name}.png')
            if loud:
                print(f'Saving {name}')
            layer.image.save(name)
            self.layers[layer.name].image = layer.image

    def _sub_cache(self, loud=True):
        for name, layer in self.layers.items():
            filename = os.path.join(self.cache_dir, f'{layer.name}.png')
            if os.path.exists(filename):
                image = Image.open(filename)
                layer.sub_image(image)
                if loud:
                    print(f'Loaded {name}')
            elif loud:
                print(f'No cached image for {name}')

    def make_new_image(self, layer=None, color=(0,0,0,0)):
        if layer is None:
            size = self.size
        else:
            a = self.layers[layer]
            size = (a.width, a.height)

        return Image.new('RGBA', size, color)

    def paste(self, base_image, paste_image):
        if isinstance(paste_image, str):
            paste_image = self.layers[paste_image].image

        if paste_image.has_transparency_data:
            base_image.paste(paste_image, (0,0), paste_image)
        else:
            base_image.paste(paste_image, (0,0))

    def paste_group(self, base_image, group_name):
        for paste_image in self.groups[group_name]:
            self.paste(base_image, paste_image)

    def scale_to_tiles(self, base_image, pixel_size, tile_size):
        scale_factor = tile_size*8/pixel_size
        w,h = base_image.size
        w*=scale_factor
        h*=scale_factor
        w = int(round(w))
        h = int(round(h))
        return base_image.resize((w,h))

    def pad_layer_bounds(self, layer, amount):
        layer.xOffset -= amount
        layer.yOffset -= amount
        layer.width += amount*2
        layer.height += amount*2
        layer.image = ImageOps.expand(layer.image, amount, (0,0,0,0))


    def expand_layers(self, layer_group, amount):
        for name in self.groups[layer_group]:
            layer = self.layers[name]
            self.pad_layer_bounds(layer, amount)
            a = pil_to_cv(layer.image)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (amount, amount))
            a = cv2.dilate(a, kernel, iterations=1)
            a = cv_to_pil(a)
            layer.image = a



    def _get_layer_bbox(self, layer):
        x, y, w, h = (layer.xOffset, layer.yOffset, layer.width, layer.height)
        dx, dy, dw, dh = layer.image.getbbox()
        dw -= dx
        dh -= dy
        bbox = (x+dx,y+dy,x+dx+dw,y+dy+dh)
        return bbox

    def mask_layers(self, target_layer, mask_layer, crop_to_mask = False) -> Image:
        if isinstance(target_layer, str):
            target_layer = self.layers[target_layer]
        if isinstance(mask_layer, str):
            mask_layer = self.layers[mask_layer]

        if isinstance(mask_layer, WrappedLayer):
            if crop_to_mask:
                bbox = self._get_layer_bbox(mask_layer)
                pixel_size, tile_size = self._get_export_sizes(None, None)
                grid_offset = self.get_grid_offset('r')
                ebbox = self.expand_bbox_to_tiles(bbox, grid_offset, pixel_size, tile_size)

            mask_layer = mask_layer.image
        else:
            if crop_to_mask:
                raise ValueError('mask must be layer to crop to mask')
        if isinstance(target_layer, WrappedLayer):
            target_layer = target_layer.image

        if crop_to_mask:
            result = target_layer.crop(ebbox)
            dl = bbox[0] - ebbox[0]
            dt = bbox[1] - ebbox[1]
            dr = ebbox[2] - bbox[2]
            db = ebbox[3] - bbox[3]

            dw = dl+dr
            dh = dt+db

            mask_layer = mask_layer.crop(mask_layer.getbbox())
            mask_layer = ImageOps.expand(mask_layer, (dl, dt, dr, db))
        else:
            result = target_layer.copy()

        alpha = mask_layer.getchannel('A')
        try:
            alpha = ImageChops.multiply(alpha, result.getchannel('A'))
        except ValueError:
            pass
        result.putalpha(alpha)

        return result

    def extract_sprite_frames(self, composed_frame: Image, sprite_group = 'sprites'):

        for sprite_name in self.groups[sprite_group]:
            out_frame = self.mask_layers(composed_frame, sprite_name, crop_to_mask=True)

            _frames = self.sprites.setdefault(sprite_name, [])
            _frames.append(out_frame)


    def get_grid_offset(self, varname, pixel_size = None, tile_size = None):
        """
        get average grid offset in image pixels from a list of coordinates
        """
        coords = list(self.variables[varname])

        pixel_size,tile_size = self._get_export_sizes(pixel_size, tile_size)
        scale_factor = tile_size/pixel_size

        for idx, vals in enumerate(coords):

            vals = tuple(x*scale_factor for x in vals)
            vals = tuple(x-int(x) for x in vals)
            vals = tuple(x/scale_factor for x in vals)

            coords[idx] = vals

        cols = list(zip(*coords))

        avgs = [sum(x)/len(x) for x in cols]
#        devs = [np.std(x) for x in cols]

        return avgs

    def expand_bbox_to_tiles(self, bbox, grid_offset, pixel_size, tile_size):
        left, top, right, bot = bbox

        grid_size = pixel_size/tile_size #px per tile

        #gx + gs*N = left
        #N = (left-gx)/gs

        left = math.floor((left-grid_offset[0])/grid_size)*grid_size + grid_offset[0]
        right = math.ceil((right-grid_offset[0])/grid_size)*grid_size + grid_offset[0]

        top = math.floor((top-grid_offset[1])/grid_size)*grid_size + grid_offset[1]
        bot = math.ceil((bot-grid_offset[1])/grid_size)*grid_size + grid_offset[1]

        new_bbox = left, top, right, bot

        new_bbox = [round(x) for x in new_bbox]

        return new_bbox


    def _get_export_sizes(self, pixel_size, tile_size):
        if pixel_size is None:
            try:
                pixel_size = self.variables['pixel_size']
            except KeyError:
                raise KeyError(f'No pixel_size specified in project {self.variables.keys()}')
        if tile_size is None:
            try:
                tile_size = self.variables['tile_size']
            except KeyError:
                raise KeyError(f'No tile_size specified in project {self.variables.keys()}')
        return pixel_size, tile_size

    def export_sprites_gif(self, output_dir, pixel_size = None, tile_size = None, gui_scale = False, **custom_gif_kwargs):
        gif_kwargs = {
            'duration': 100,
            'loop': 0,
            'disposal': 2,
        }
        gif_kwargs.update(custom_gif_kwargs)

        pixel_size, tile_size = self._get_export_sizes(pixel_size, tile_size)

        if gui_scale:
            tile_size *= 6

        for sprite_name, frames in sorted(self.sprites.items()):
            print(f'Writing {sprite_name}')
            frames = [self.scale_to_tiles(x, pixel_size, tile_size) for x in frames]
            base = frames[0]
            base.save(os.path.join(output_dir, f'{sprite_name}.gif'), save_all=True, append_images=frames[1:], **gif_kwargs)

    def export_sprites(self, output_dir, pixel_size=None, tile_size=None, gui_scale = False):
        pixel_size, tile_size = self._get_export_sizes(pixel_size, tile_size)

        if gui_scale:
            tile_size *= 6

        for sprite_name, frames in sorted(self.sprites.items()):
            print(f'Writing {sprite_name}')
            frames = [self.scale_to_tiles(x, pixel_size, tile_size) for x in frames]
            for idx, frame in enumerate(frames):
                frame.save(os.path.join(output_dir,f'{sprite_name}{idx:02}.png'))




