import math
import os
import json

from collections import defaultdict

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageOps, ImageTransform

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

class SpriteMask():
    def __init__(self, contours, label, size, ref_points = None):
        self.contours = contours
        self.label = label
        self.size = size

        self.angle = None
        if ref_points is not None:
            dx = ref_points[1][0] - ref_points[0][0]
            dy = ref_points[1][1] - ref_points[0][1]
            self.angle = math.atan2(dy, dx)*180/math.pi
            print(f'{label}: {self.angle}')

        self.render_mask()

    def render_mask(self):
        #I don't want to think about w/h ordering or w/e
        image = Image.new('L', self.size, 0)
        image = np.array(image)
        cv2.drawContours(image, self.contours, -1, 255, -1)
        image = Image.fromarray(image)
        self.image = image

    def _bbox(self, cnt):
        x,y,w,h = cv2.boundingRect(cnt)
        l = x
        r = x+w
        t = y
        b = y+h
        return l, t, r, b

    def get_bbox(self):
        l, t, r, b = self._bbox(self.contours[0])
        for cnt in self.contours[1:]:
            nl, nt, nr, nb = self._bbox(cnt)
            l = min(nl, l)
            r = max(nr, r)
            t = min(nt, t)
            b = max(nb, b)

        return l, r, t, b



class GimpProject():
    def __init__(self, project_dir):

        self.project_dir = project_dir

        self.filename = os.path.join(project_dir, 'inputs.xcf')
        self.cache_dir = os.path.join(project_dir, 'gimp_cache')
        self.output_dir = os.path.join(project_dir, 'outputs')
        self.data = GimpDocument(self.filename)

        gato_file = os.path.join(project_dir, 'gato.json')
        segs_file = os.path.join(project_dir, 'segs.json')

        self.gato_config = None
        if os.path.exists(gato_file):
            with open(gato_file, 'r') as fp:
                self.gato_config = json.load(fp)

        self.segs_config = None
        if os.path.exists(segs_file):
            with open(segs_file, 'r') as fp:
                self.segs_config = json.load(fp)

        os.makedirs(self.cache_dir, exist_ok=True)
        self.init_layers()
        self.update_cache()
        self._sub_cache(loud=False)

        self.init_sprites('sprites')

    def init_sprites(self, layer_name, bonus_prefix = ''):
        self.sprites = {}

        self.sprite_masks = []

        if self.segs_config is None:
            return

        contours = self.get_layer_segments(layer_name, self.segs_config['padding'])
        labels = self.segs_config['labels']
        prefix = self.segs_config['prefix']

        label_map = defaultdict(list)
        ref_map = {}

        for cnt in contours:
            for entry in labels:
                name = entry[0]
                point = entry[1]
                ref_points = None
                if len(entry) > 2:
                    ref_points = entry[2]
                if cv2.pointPolygonTest(cnt, point, False) <= 0:
                    continue
                label = prefix+name
                label_map[label].append(cnt)
                if ref_points is not None:
                    ref_map[label] = ref_points
                break

        for label, contours in label_map.items():
            self.sprite_masks.append(SpriteMask(contours, bonus_prefix+label, self.size, ref_map.get(label)))

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

    def get_layer_cache_file(self, layer):
        return os.path.join(self.cache_dir, f'{layer.name}.png')


    def export_layers(self, layer_group = None, loud=True):
        for layer in self.data.layers:
            if layer_group is not None and layer.name not in self.groups[layer_group]:
                continue
            if layer.isGroup:
                continue
            self.cache_layer(layer, loud)

    def update_cache(self):
        gimp_stamp = os.path.getmtime(self.filename)
        for layer in self.data.layers:
            if layer.isGroup:
                continue
            filename = self.get_layer_cache_file(layer)
            if os.path.exists(filename):
                stamp = os.path.getmtime(filename)
            else:
                stamp = None

            if stamp is None or gimp_stamp > stamp:
                self.cache_layer(layer, loud= True)

    def cache_layer(self, layer, loud):
            name = self.get_layer_cache_file(layer)
            if loud:
                print(f'Saving {name}')
            layer.image.save(name)
            self.layers[layer.name].image = layer.image

    def _sub_cache(self, loud=True):
        for name, layer in self.layers.items():
            filename = self.get_layer_cache_file(layer)
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


    def expand_layers(self, layer_group, amount, pad_bounds = True):
        for name in self.groups[layer_group]:
            self.expand_layer(name, amount, pad_bounds)

    def expand_layer(self, name, amount, pad_bounds = True):
        layer = self.layers[name]
        layer.image = self.get_expanded_layer(name, amount, pad_bounds)

    def get_expanded_layer(self, layer, amount, pad_bounds = True):
        if isinstance(layer, str):
            layer = self.layers[layer]

        if pad_bounds:
            self.pad_layer_bounds(layer, amount)

        a = pil_to_cv(layer.image)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (amount, amount))
        a = cv2.dilate(a, kernel, iterations=1)
        a = cv_to_pil(a)
        return a


    def get_layer_segments(self, layer, expansion = 0):
        if isinstance(layer, str):
            layer = self.layers[layer]

        if expansion != 0:
            image = self.get_expanded_layer(layer, expansion, pad_bounds=False)
        else:
            image = layer.image

        image = pil_to_cv(image)

        _,_,_,alpha = cv2.split(image)

        ret, thresh = cv2.threshold(alpha, 127,255,0)
        contours, hierarchy = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        return contours

    def map_segment_labels(self, contours, labels):
        result = {}

        for cnt in contours:
            for label, point in labels.items():
                if cv2.pointPolygonTest(cnt, point, False) > 0:
                    if label in result.keys():
                        print(f'Warning: label {label} ({point}) matches multiple segments')
                    result[label] = cnt
                    break
            else:
                print(f'Warning: no matching segment for {label}: {point}')

        return result

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
                grid_offset = self.get_grid_offset()
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

    def extract_sprite_frames(self, composed_frame: Image, suffix = None, filter_func = None):

        result = {}

        for sprite_mask in self.sprite_masks:
            sprite_name = sprite_mask.label
            if filter_func is not None and not filter_func(sprite_name):
                continue

            if suffix is not None:
                sprite_name += suffix
            mask = sprite_mask.image
            bbox = mask.getbbox()

            pixel_size, tile_size = self._get_export_sizes(None, None)
#            grid_offset = self.get_grid_offset()
#            grid_offset = self.get_nearest_grid_offset((bbox[0], bbox[1]))
            ebbox = self.expand_bbox_to_tiles(bbox, None, pixel_size, tile_size, do_round = False)

            out_frame = composed_frame.copy()
            alpha = ImageChops.multiply(mask, composed_frame.getchannel('A'))
            out_frame.putalpha(alpha)

            w = math.ceil(ebbox[2]-ebbox[0])
            h = math.ceil(ebbox[3]-ebbox[1])

#            out_frame = out_frame.crop(ebbox)
            out_frame = out_frame.transform((w,h), Image.Transform.EXTENT, ebbox, resample=Image.Resampling.BILINEAR)

            if sprite_mask.angle is not None:
                out_frame = out_frame.rotate(sprite_mask.angle, resample=Image.Resampling.BICUBIC, expand=True)

            _frames = self.sprites.setdefault(sprite_name, [])
            _frames.append(out_frame)
            result[sprite_name] = out_frame

        return result


    def get_grid_offset(self, pixel_size = None, tile_size = None):
        """
        get average grid offset in image pixels from a list of coordinates
        """

        coords = list(self.gato_config['alignment_grid']['grid']['refs'])

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

    def get_nearest_grid_offset(self, point, pixel_size = None, tile_size = None):
        """
        get the grid offset based on the point nearest the given coordinate
        """

        coords = list(self.gato_config['alignment_grid']['grid']['refs'])

        def dist(x,y):
            return (x[0]-y[0])**2+(x[1]-y[1])**2

        coords = list(sorted(coords, key = lambda x: dist(x, point)))

        pixel_size,tile_size = self._get_export_sizes(pixel_size, tile_size)
        scale_factor = tile_size/pixel_size

        vals = coords[0]

        vals = tuple(x*scale_factor for x in vals)
        vals = tuple(x-int(x) for x in vals)
        vals = tuple(x/scale_factor for x in vals)

        return vals


    def expand_bbox_to_tiles(self, bbox, grid_offset, pixel_size, tile_size, do_round = True):
        left, top, right, bot = bbox

        grid_size = pixel_size/tile_size #px per tile

        #gx + gs*N = left
        #N = (left-gx)/gs
        dynamic_offset = grid_offset is None
        if dynamic_offset:
            grid_offset = self.get_nearest_grid_offset((left, top), pixel_size, tile_size)

        left = math.floor((left-grid_offset[0])/grid_size)*grid_size + grid_offset[0]
        top = math.floor((top-grid_offset[1])/grid_size)*grid_size + grid_offset[1]

        if dynamic_offset:
            grid_offset = self.get_nearest_grid_offset((right, bot), pixel_size, tile_size)

        right = math.ceil((right-grid_offset[0])/grid_size)*grid_size + grid_offset[0]
        bot = math.ceil((bot-grid_offset[1])/grid_size)*grid_size + grid_offset[1]

        #expand to even number of tiles
        wn = round((right-left)/grid_size)
        hn = round((bot-top)/grid_size)

        if wn % 2:
            left -= grid_size

        if hn % 2:
            top -= grid_size

        new_bbox = left, top, right, bot

        if do_round:
            new_bbox = [round(x) for x in new_bbox]

        return new_bbox


    def _get_export_sizes(self, pixel_size, tile_size):
        if pixel_size is None:
            if self.gato_config is not None:
                pixel_size = self.gato_config['alignment_grid']['grid']['pixel_size']
            else:
                try:
                    pixel_size = self.variables['pixel_size']
                except KeyError:
                    raise KeyError(f'No pixel_size specified in project {self.variables.keys()}')
        if tile_size is None:
            if self.gato_config is not None:
                tile_size = self.gato_config['alignment_grid']['grid']['tile_size']
            else:
                try:
                    tile_size = self.variables['tile_size']
                except KeyError:
                    raise KeyError(f'No tile_size specified in project {self.variables.keys()}')
        if tile_size > pixel_size:
            raise ValueError(f'{pixel_size=} < {tile_size=}')

        return pixel_size, tile_size

    def fix_sprite_name(self, name):
        try:
            int(name[-1])
            return name+'.'
        except:
            return name

    def export_sprites_gif(self, output_dir, pixel_size = None, tile_size = None, gui_scale = False, sprite_scale = 1, sprite_prefix = '', **custom_gif_kwargs):
        output_dir = os.path.join(self.output_dir, output_dir)
        os.makedirs(output_dir, exist_ok = True)
        gif_kwargs = {
            'duration': 100,
            'loop': 0,
            'disposal': 2,
        }
        gif_kwargs.update(custom_gif_kwargs)

        pixel_size, tile_size = self._get_export_sizes(pixel_size, tile_size)

        if gui_scale:
            tile_size *= 6

        tile_size *= sprite_scale

        for sprite_name, frames in sorted(self.sprites.items()):
            sprite_name = sprite_prefix+sprite_name
            print(f'Writing {sprite_name}')
            frames = [self.scale_to_tiles(x, pixel_size, tile_size) for x in frames]
            base = frames[0]
            base.save(os.path.join(output_dir, f'{sprite_name}.gif'), save_all=True, append_images=frames[1:], **gif_kwargs)

    def export_sprites(self, output_dir, pixel_size=None, tile_size=None, gui_scale = False, sprite_scale=1, sprite_prefix = ''):
        output_dir = os.path.join(self.output_dir, output_dir)
        os.makedirs(output_dir, exist_ok = True)

        pixel_size, tile_size = self._get_export_sizes(pixel_size, tile_size)

        if gui_scale:
            tile_size *= 6

        tile_size *= sprite_scale

        for sprite_name, frames in sorted(self.sprites.items()):
            sprite_name = sprite_prefix+sprite_name
            print(f'Writing {sprite_name}')
            frames = [self.scale_to_tiles(x, pixel_size, tile_size) for x in frames]
            sprite_name = self.fix_sprite_name(sprite_name)
            for idx, frame in enumerate(frames):
                frame_name = sprite_name
                if len(frames) > 1:
                    frame_name += f'{idx:02}'
                frame.save(os.path.join(output_dir,f'{frame_name}.png'))




