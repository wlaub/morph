import os

from collections import defaultdict

from PIL import Image, ImageChops

from gimpformats.gimpXcfDocument import GimpDocument

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

    def init_layers(self):
        self.layers = {}
        self.groups = defaultdict(list)
        self.int_layers = []
        active_group = None
        for layer in self.data.layers:
            if layer.isGroup:
                active_group = layer.name
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

    def export_layers(self, loud=True):
        for layer in self.data.layers:
            name = os.path.join(self.cache_dir, f'{layer.name}.png')
            if loud:
                print(f'Saving {name}')
            layer.image.save(name)

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

        base_image.paste(paste_image, (0,0), paste_image)

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



    def mask_layers(self, target_layer, mask_layer, crop_to_mask = False) -> Image:
        if isinstance(target_layer, str):
            target_layer = self.layers[target_layer]
        if isinstance(mask_layer, str):
            mask_layer = self.layers[mask_layer]

        if isinstance(mask_layer, WrappedLayer):
            if crop_to_mask:
#                bbox = mask_layer.getbbox()
                x, y, w, h = (mask_layer.xOffset, mask_layer.yOffset, mask_layer.width, mask_layer.height)
                bbox = (x,y,x+w,y+h)
            mask_layer = mask_layer.image
        else:
            if crop_to_mask:
                raise ValueError('mask must be layer to crop to mask')
        if isinstance(target_layer, WrappedLayer):
            target_layer = target_layer.image

        if crop_to_mask:
            result = target_layer.crop(bbox)
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
#            out_frame = self.scale_to_tiles(out_frame, pixel_size, tile_size)

            _frames = self.sprites.setdefault(sprite_name, [])
            _frames.append(out_frame)

    def export_sprites_gif(self, output_dir, pixel_size, tile_size, gui_scale = False, **custom_gif_kwargs):
        gif_kwargs = {
            'duration': 100,
            'loop': 0,
            'disposal': 2,
        }
        gif_kwargs.update(custom_gif_kwargs)

        if gui_scale:
            tile_size *= 6

        for sprite_name, frames in self.sprites.items():
            print(f'Writing {sprite_name}')
            frames = [self.scale_to_tiles(x, pixel_size, tile_size) for x in frames]
            base = frames[0]
            base.save(os.path.join(output_dir, f'{sprite_name}.gif'), save_all=True, append_images=frames[1:], **gif_kwargs)

    def export_sprites(self, output_dir, pixel_size, tile_size, gui_scale = False):
        if gui_scale:
            tile_size *= 6

        for sprite_name, frames in self.sprites.items():
            print(f'Writing {sprite_name}')
            frames = [self.scale_to_tiles(x, pixel_size, tile_size) for x in frames]
            for idx, frame in enumerate(frames):
                frame.save(os.path.join(output_dir,f'{sprite_name}{idx:02}.png'))




