import os
import time
import math
import json
from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops, ImageEnhance

from morphsuit import morph, gimp

import pygame
import pygame.gfxdraw
import pygame.transform
from pygame.locals import *

import crossfiledialog as cfd
import platformdirs

#TODO
"""
Angle selection controls
Export images
"""

LMB = 1
MMB = 2
RMB = 3

pygame.init()
pygame.font.init()

font = pygame.font.Font(size=24)

width, height = 1500,1000
GN = 3
cheight = height
cwidth = cheight


screen=pygame.display.set_mode((width, height))

def image_to_surface(image):
    return pygame.image.fromstring(image.tobytes(), image.size, image.mode)

def surface_to_image(surface):
    return Image.frombytes("RGB", surface.get_size(),
        pygame.image.tobytes(surface, "RGB", False)
        )

class AppConfig:
    def __init__(self):
        self.config_dir = platformdirs.user_data_dir('gato')
        self.config_file = os.path.join(self.config_dir, 'state.json')

        self.config = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as fp:
                self.config = json.load(fp)

    def save(self):
        os.makedirs(self.config_dir, exist_ok = True)
        with open(self.config_file, 'w') as fp:
            json.dump(self.config, fp)

app_config = AppConfig()

def memory_select(callback, **kwargs):
    kwargs['start_dir'] = app_config.config.get('start_dir', os.path.expanduser('~'))
    result = callback(**kwargs)

    if result == '' or result is None:
        return None

    if not isinstance(result, str):
        ref = result[0]
    else:
        ref = result

    app_config.config['start_dir'] = os.path.dirname(result)
    app_config.save()

    return result


class CropBox():
    def __init__(self, base_image, data = None):
        self.base_image = base_image

        if data is None: data = {}
        self.ul = data.get('ul') or (0,0)
        self.lr = data.get('lr') or base_image.size
        self.update_params()

        self.active = False
        self.drag_corner = False
        self.sel_corner = 0

        self.eul = None
        self.elr = None
        self.parent = None

        self.on_change = []

    def update_image(self, base_image):
        self.base_image = base_image
        self.update_params()

    def to_json(self):
        return {'ul': self.ul, 'lr': self.lr}

    def crop_to_box(self, other):
        self.ul = list(self.ul)
        self.lr = list(self.lr)
        if self.ul[0] < other.ul[0]:
            self.ul[0] = other.ul[0]
        if self.ul[1] < other.ul[1]:
            self.ul[1] = other.ul[1]
        if self.lr[0] > other.lr[0]:
            self.lr[0] = other.lr[0]
        if self.lr[1] > other.lr[1]:
            self.lr[1] = other.lr[1]
        self.ul = tuple(self.ul)
        self.lr = tuple(self.lr)
        self.changed()

    def changed(self):
        for callback in self.on_change:
            callback()

    def crop_to_parent(self):
        self.crop_to_box(self.parent)

    def set_parent(self, parent):
        self.parent = parent
        self.crop_to_box(parent)

    def from_screen(self, pos):
        if self.parent is not None:
            return self.parent.from_screen(pos)

        x = pos[0]/self.crop_scale + self.ul[0]
        y = pos[1]/self.crop_scale + self.ul[1]
        return (x,y)

    def to_screen(self, pos):
        if self.parent is not None:
            return self.parent.to_screen(pos)

        x = (pos[0] - self.ul[0])*self.crop_scale
        y = (pos[1] - self.ul[1])*self.crop_scale
        return (x,y)

    def get_bbox(self):
        return (*self.ul, *self.lr)

    def get_size(self):
        return tuple(self.lr[i]-self.ul[i] for i in [0,1])

    def get_corners(self):
        """
        ul ur lr ll
        """
        ul = self.ul
        ur = (self.lr[0], self.ul[1])
        lr = self.lr
        ll = (self.ul[0], self.lr[1])
        return ul, ur, lr, ll

    def activate(self, mpos):
        if self.active: return
        self.active = True

        mpos = self.from_screen(mpos)
        self.eul = self.ul
        self.elr = self.lr

        s = 100

        for idx, cpos in enumerate(self.get_corners()):
            if (cpos[0]-mpos[0])**2 + (cpos[1]-mpos[1])**2 < s**2:
                self.drag_corner = True
                self.sel_corner = idx
                return

        self.drag_corner = False
        self.eul = mpos
        self.elr = self.eul

    def abort(self):
        self.active = False

    def update(self, mpos):
        if not self.active: return
        mpos = self.from_screen(mpos)

        if not self.drag_corner:
            self.elr = mpos
            return

        if self.sel_corner == 0:
            self.eul = mpos
        elif self.sel_corner == 1:
            self.eul = (self.eul[0], mpos[1])
            self.elr = (mpos[0], self.elr[1])
        elif self.sel_corner == 2:
            self.elr = mpos
        elif self.sel_corner == 3:
            self.elr = (self.elr[0], mpos[1])
            self.eul = (mpos[0], self.eul[1])


    def finish(self, mpos):
        if not self.active: return False
        self.apply_changes()
        return True

    def correct_corners(self, ul, lr):
        l = min(ul[0], lr[0])
        r = max(ul[0], lr[0])
        t = min(ul[1], lr[1])
        b = max(ul[1], lr[1])
        return (l, t), (r, b)

    def apply_changes(self):
        if not self.active: return
        self.active = False
        if self.eul[0] == self.elr[0] or self.eul[1] == self.elr[1]:
            return

        self.ul, self.lr = self.correct_corners(self.eul, self.elr)
        self.update_params()
        self.changed()

    def update_params(self):
        gw, gh = self.get_size()
        self.crop_scale = min(cheight/gh, cwidth/gw)

    def get_cropped_surface(self):
        bbox = self.get_bbox()
        cropped_image = self.base_image.crop(bbox)
        cropped_surface = image_to_surface(cropped_image)
        return pygame.transform.scale_by(cropped_surface, self.crop_scale)

    def render(self, screen, color):
        if self.active:
            ul = self.eul
            lr = self.elr
        else:
            ul = self.ul
            lr = self.lr

        ul = self.to_screen(ul)
        lr = self.to_screen(lr)

        csize = [lr[x]-ul[x] for x in [0,1]]
        crect = pygame.Rect(ul, csize)
        pygame.gfxdraw.rectangle(screen, crect, color)

    def __str__(self):
        return f'{self.ul[0]:.2f}, {self.ul[1]:.2f}, {self.lr[0]:.2f}, {self.lr[1]:0.2f}'

def intersect(p, q, r, s):
    x1, y1 = p
    x2, y2 = q
    x3, y3 = r
    x4, y4 = s

    a = (x1*y2-y1*x2)
    b = (x3*y4-y3*x4)
    den = (x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
    x = (a*(x3-x4) - b*(x1-x2))/den
    y = (a*(y3-y4) - b*(y1-y2))/den

    return x,y

class GridControl():
    def __init__(self, base_image, alignment_box, crop_box, data = None):
        self.crop_box = crop_box
        self.base_image = base_image
        self.alignment_box = alignment_box

        self.active = False
        self.sel_idx = 0
        self.sel_ref = None

        self.compute_params()
        if data is None:
            self.init_refs()
            self.grayscale = 1
            self.contrast = 1
            self.brightness = 1
            self.sharpness = 1
        else:
            self.load(data)


        self.update_image()

    def update_image(self, base_image = None):
        if base_image is not None:
            self.base_image = base_image
        self.background_surface_raw = self.render_base()
        self.background_surface = self.apply_contrast()

    def fix_refs(self, data):
        for key in list(data.keys()):
            data[int(key)] = data.pop(key)
        return data

    def load(self, data):
        self.vrefs = self.fix_refs(data['vrefs'])
        self.hrefs = self.fix_refs(data['hrefs'])
        self.grayscale = data['color']['grayscale']
        self.contrast = data['color']['contrast']
        self.brightness = data['color']['brightness']
        self.sharpness = data['color']['sharpness']

    def to_json(self):
        pixel_size, tile_size, grid_size = self.compute_grid_params()
        result = {
            'vrefs': self.vrefs,
            'hrefs': self.hrefs,
            'color': {
                'grayscale': self.grayscale,
                'contrast': self.contrast,
                'brightness': self.brightness,
                'sharpness': self.sharpness,
                },
            'grid': {
                'refs': self.compute_grid_points(),
                'pixel_size': pixel_size,
                'tile_size': tile_size,
                },
            }

        return result

    def do_contrast(self, x):
        self.contrast += x/10
        if self.contrast < 0:
            self.contrast = 0
        self.background_surface = self.apply_contrast()

    def do_brightness(self, x):
        self.brightness += x/10
        if self.brightness < 0:
            self.brightness = 0
        self.background_surface = self.apply_contrast()

    def do_sharpness(self, x):
        self.sharpness += x/10
        if self.sharpness < 0:
            self.sharpness = 0
        self.background_surface = self.apply_contrast()

    def do_grayscale(self, x):
        self.grayscale += x/10
        if self.grayscale < 0:
            self.grayscale = 0
        self.background_surface = self.apply_contrast()

    def render_base(self):
        ul = self.alignment_box.ul
        lr = self.alignment_box.lr

        csize = self.csize
        gbw = self.gbw; gbh = self.gbh
        giw = self.giw; gih = self.gih
        dx = self.dx; dy = self.dy

        result = pygame.Surface((giw*GN, gih*GN))

        grid_surface = image_to_surface(self.base_image)

        for x in range(GN):
            for y in range(GN):
                xpos = ul[0] + x*dx
                ypos = ul[1] + y*dy
                result.blit(grid_surface, (int(x*giw), int(y*gih)),
                    pygame.Rect(int(xpos), int(ypos), int(giw), int(gih))
                    )

        sf = gbw/giw
        result = pygame.transform.scale_by(result, sf)
        return result

    def get_boxes(self):
        if self.alignment_box.active:
            ul = self.alignment_box.eul
            lr = self.alignment_box.elr

            csize = [lr[x]-ul[x] for x in [0,1]]

            gbw = cwidth/GN
            gbh = cheight/GN

            giw = 100
            gih = giw*gbh/gbw

            dx = (csize[0]-giw)/(GN-1)
            dy = (csize[1]-gih)/(GN-1)
        else:
            ul = self.alignment_box.ul
            lr = self.alignment_box.lr

            csize = self.csize
            gbw = self.gbw; gbh = self.gbh
            giw = self.giw; gih = self.gih
            dx = self.dx; dy = self.dy

        result = []

        for x in range(GN):
            for y in range(GN):
                xpos = ul[0] + x*dx
                ypos = ul[1] + y*dy
                result.append([(xpos, ypos), (xpos+giw, ypos+giw)])

        return result


    def apply_contrast(self):
        result = surface_to_image(self.background_surface_raw)

        result = ImageEnhance.Color(result).enhance(self.grayscale)
        result = ImageEnhance.Brightness(result).enhance(self.brightness)
        result = ImageEnhance.Contrast(result).enhance(self.contrast)
        result = ImageEnhance.Sharpness(result).enhance(self.sharpness)

        result = image_to_surface(result)

        return result


    def init_refs(self):
        ul = self.alignment_box.ul
        lr = self.alignment_box.lr

        csize = self.csize
        gbw = self.gbw; gbh = self.gbh
        giw = self.giw; gih = self.gih
        dx = self.dx; dy = self.dy

        self.vrefs = {}
        self.hrefs = {}
        for x in range(GN):
            self.vrefs[x] = [
                (ul[0]+x*dx+giw/2, ul[1]+0*dy+gih/2-20),
                (ul[0]+x*dx+giw/2, ul[1]+(GN-1)*dy+gih/2+20),
                ]
            self.hrefs[x] = [
                (ul[0]+0*dx+giw/2-20, ul[1]+x*dy+gih/2),
                (ul[0]+(GN-1)*dx+giw/2+20, ul[1]+x*dy+gih/2),
                ]

    def compute_params(self):
        ul = self.alignment_box.ul
        lr = self.alignment_box.lr

        self.csize = csize = [lr[x]-ul[x] for x in [0,1]]

        self.gbw = gbw = cwidth/GN
        self.gbh = gbh = cheight/GN

        self.giw = giw = 100
        self.gih = gih = giw*gbh/gbw

        self.dx = dx = (csize[0]-giw)/(GN-1)
        self.dy = dy = (csize[1]-gih)/(GN-1)

    def activate(self, mpos):
        if self.active: return

        ul = self.alignment_box.ul
        lr = self.alignment_box.lr

        csize = self.csize
        gbw = self.gbw; gbh = self.gbh
        giw = self.giw; gih = self.gih
        dx = self.dx; dy = self.dy

        xs, ys = mpos

        xi = int(xs/gbw)
        yi = int(ys/gbw)

        if xi != 0 and xi != GN-1 and yi != 0 and yi != GN-1:
            return

        x = ul[0] + dx*xi + (xs-xi*gbw)*giw/gbw
        y = ul[1] + dy*yi + (ys-yi*gbw)*gih/gbh

        all_points = []
        for i in range(GN):
            p,q = self.vrefs[i]
            all_points.append([p, i, 0, self.vrefs])
            all_points.append([q, i, 1, self.vrefs])
            p,q = self.hrefs[i]
            all_points.append([p, i, 0,  self.hrefs])
            all_points.append([q, i, 1,  self.hrefs])

        search_points = []
        for entry in all_points:
            p = entry[0]
            dist = (p[0]-x)**2 + (p[1]-y)**2
            if dist < 30*30:
                search_points.append([dist, *entry])

        if len(search_points) == 0:
            return

        search_points = list(sorted(search_points, key=lambda x: x[0]))

        self.sel_idx = search_points[0][2]
        self.sel_sub_idx = search_points[0][3]
        self.sel_ref = search_points[0][4]

        self.active = True

    def update(self, mpos):
        if not self.active: return

        ul = self.alignment_box.ul
        lr = self.alignment_box.lr

        csize = self.csize
        gbw = self.gbw; gbh = self.gbh
        giw = self.giw; gih = self.gih
        dx = self.dx; dy = self.dy

        xs, ys = mpos

        xi = int(xs/gbw)
        yi = int(ys/gbw)

        if xi != 0 and xi != GN-1 and yi != 0 and yi != GN-1:
            return

        x = ul[0] + dx*xi + (xs-xi*gbw)*giw/gbw
        y = ul[1] + dy*yi + (ys-yi*gbw)*gih/gbh

        self.sel_ref[self.sel_idx][self.sel_sub_idx] = (x,y)


    def finish(self, mpos):
        if not self.active: return False
        self.active = False
        return True

    def render(self, screen):
        screen.blit(self.background_surface, (0,0))

        ul = self.alignment_box.ul
        lr = self.alignment_box.lr

        csize = self.csize
        gbw = self.gbw; gbh = self.gbh
        giw = self.giw; gih = self.gih
        dx = self.dx; dy = self.dy

        def cmap(p, xi, yi):
            x = (p[0]-ul[0]-dx*xi)*gbw/giw + xi*gbw
            y = (p[1]-ul[1]-dy*yi)*gbh/gih + yi*gbh
            return x,y


        color = (255,0,255)
        for i in range(GN):
            p, q = self.vrefs[i]

            for j in range(GN):

                r = (0, ul[1]+j*dy)
                s = (10, ul[1]+j*dy)

                x,y = intersect(p,q,r,s)
                x1, y1 = cmap((x,y), i, j)

                r = (0, ul[1]+j*dy+gih)
                s = (10, ul[1]+j*dy+gih)

                x,y = intersect(p,q,r,s)
                x2, y2 = cmap((x,y), i, j)

                pygame.gfxdraw.line(screen,
                    int(x1), int(y1), int(x2), int(y2),
                    color)

            x,y = cmap(p, i, 0)
            pygame.gfxdraw.filled_circle(screen, int(x), int(y), 7, color)
            x,y = cmap(q, i, GN-1)
            pygame.gfxdraw.filled_circle(screen, int(x), int(y), 7, color)


            p, q = self.hrefs[i]

            for j in range(GN):

                r = (ul[0]+j*dx, 0)
                s = (ul[0]+j*dx, 10)

                x,y = intersect(p,q,r,s)
                x1, y1 = cmap((x,y), j,i)

                r = (ul[0]+j*dx+giw, 0)
                s = (ul[0]+j*dx+giw, 10)

                x,y = intersect(p,q,r,s)
                x2, y2 = cmap((x,y), j,i)

                pygame.gfxdraw.line(screen,
                    int(x1), int(y1), int(x2), int(y2),
                    color)

            x,y = cmap(p, 0, i)
            pygame.gfxdraw.filled_circle(screen, int(x), int(y), 7, color)
            x,y = cmap(q, GN-1, i)
            pygame.gfxdraw.filled_circle(screen, int(x), int(y), 7, color)


    def compute_angles(self):

        def get_angle(a,b):
            dx = a[0]-b[0]
            dy = a[1]-b[1]
            res = math.atan2(dy, dx)*180/math.pi
            res -= round(res/90)*90
            return res

        hangles = []
        vangles = []

        for i in range(GN):
            p,q = self.hrefs[i]
            hangles.append(get_angle(p,q))
            p,q = self.vrefs[i]
            vangles.append(get_angle(p,q))

        return hangles, vangles

    def compute_grid_points(self, ):
        result = []
        ul = self.crop_box.ul
        for i in range(GN):
            p, q = self.hrefs[i]
            for j in range(GN):
                r,s = self.vrefs[i]
                a = intersect(p,q,r,s)
                a = (a[0]-ul[0], a[0]-ul[1])
                result.append(a)
        return result

    def compute_grid_params(self):
        l = (   self.vrefs[0][0][0]   +self.vrefs[0][1][0])/2
        r = (self.vrefs[GN-1][0][0]+self.vrefs[GN-1][1][0])/2
        t = (   self.hrefs[0][0][1]   +self.hrefs[0][1][1])/2
        b = (self.hrefs[GN-1][0][1]+self.hrefs[GN-1][1][1])/2

        w = r-l
        h = b-t
        guess = 52.7

        gx = round(w/guess)
        gy = round(h/guess)
        pixel_size = (w**2+h**2)**0.5
        tile_size = (gx**2+gy**2)**0.5
        grid_size = pixel_size/tile_size

        return pixel_size, tile_size, grid_size



class App():
    def __init__(self, screen):

        self.cal_dir = 'calibrations'
        self.cal_config = os.path.join(self.cal_dir, 'slot_9.txt') #FIXME

        self.project_dir = app_config.config.get('current_project')

        if self.project_dir is None:
            self.prompt_load()
        else:
            self.load()

    def prompt_load(self):
        project_dir = memory_select(cfd.choose_folder)
        if project_dir is not None:
            self.project_dir = project_dir
            app_config.config['current_project'] = self.project_dir
            app_config.save()
            self.load()

    def load(self):
        self.project_file = os.path.join(self.project_dir, 'gato.json')

        config = {}
        self.dirty = True
        if os.path.exists(self.project_file):
            with open(self.project_file, 'r') as fp:
                config = json.load(fp)
                self.dirty = False

        self.mode = config.get('mode', 'crop')

        self.screen = screen

        self.cache_dir = os.path.join(self.project_dir, 'gato_cache')

        self.raw_dir = os.path.join(self.project_dir, 'raw_inputs')
        self.raw_images = [x for x in os.listdir(self.raw_dir) if x.endswith('.jpg')]

        if len(self.raw_images) == 0:
            raise RuntimeError('Not a valid project dir - no raw_images')

        os.makedirs(self.cache_dir, exist_ok = True)

        self.morpher = morph.MorphProject(self.cal_config)

        grid_cache = os.path.join(self.cache_dir, 'grid.png')
        if os.path.exists(grid_cache):
            self.grid_image = Image.open(grid_cache)
        else:
            self.grid_file = os.path.join(self.raw_dir, 'grid.jpg')
            self.grid_image = Image.open(self.grid_file)
            self.grid_image = self.morpher.lens_correct(self.grid_image)
            self.grid_image.save(grid_cache)


        self.grid_surface = image_to_surface(self.grid_image)

        #Crop Controls

        self.crop_box = CropBox(self.grid_image, config.get('crop_box'))
        self.crop_surface = self.crop_box.get_cropped_surface()

        self.alignment_box = CropBox(self.grid_image, config.get('alignment_box'))
        self.alignment_box.set_parent(self.crop_box)

        def align_update():
            self.alignment_box.crop_to_parent()
        self.crop_box.on_change.append(align_update)

        #Grid Controls

        self.grid_control = GridControl(self.grid_image, self.alignment_box, self.crop_box, config.get('rotation_grid'))

        self.angle = config.get('angle', 0)

        def grid_align_update():
            self.grid_control.compute_params()
        self.alignment_box.on_change.append(grid_align_update)

        #Final Crop

        self.rotated_grid_image = self.grid_image.rotate(self.angle)

        self.cheat_box = CropBox(self.rotated_grid_image, None)
        self.rotated_grid_surface = self.cheat_box.get_cropped_surface()


        self.final_crop_box = CropBox(self.rotated_grid_image, config.get('final_crop_box'))
        self.final_crop_surface = self.final_crop_box.get_cropped_surface()
        self.final_crop_box.set_parent(self.cheat_box)

        self.final_alignment_box = CropBox(self.rotated_grid_image, config.get('final_alignment_box'))
        self.final_alignment_box.set_parent(self.final_crop_box)

        def cheat_update():
            ul = self.final_crop_box.ul
            lr = self.final_crop_box.lr
            w,h = self.cheat_box.base_image.size
            s = 50
            nul = (max(ul[0] - s,0), max(ul[1] - s,0))
            nlr = (min(lr[0] + s,w), min(lr[1] + s,h))
            self.cheat_box.ul = nul
            self.cheat_box.lr = nlr
            self.cheat_box.update_params()
            self.rotated_grid_surface = self.cheat_box.get_cropped_surface()
        cheat_update()

        self.final_crop_box.on_change.append(lambda: self.final_alignment_box.crop_to_parent())
        self.final_crop_box.on_change.append(cheat_update)

        #Final Grid

        self.alignment_grid_control = GridControl(self.rotated_grid_image, self.final_alignment_box, self.final_crop_box, config.get('alignment_grid'))

        def align_grid_align_update():
            self.alignment_grid_control.compute_params()
        self.final_alignment_box.on_change.append(align_grid_align_update)

    def save(self):
        data = {
            'mode': self.mode,
            'angle': self.angle,
            'crop_box': self.crop_box.to_json(),
            'alignment_box': self.alignment_box.to_json(),
            'rotation_grid': self.grid_control.to_json(),
            'final_crop_box': self.final_crop_box.to_json(),
            'final_alignment_box': self.final_alignment_box.to_json(),
            'alignment_grid': self.alignment_grid_control.to_json()
            }
        with open(self.project_file, 'w') as fp:
            json.dump(data, fp, indent = 2)
        self.dirty = False

    def update_alignment_angle(self):
        #TODO this might need a way to select from different values
        ha, va = self.grid_control.compute_angles()
        self.angle = sum(va)/len(va)

    def update_aligned_image(self):
        self.update_alignment_angle()
        self.rotated_grid_image = self.grid_image.rotate(self.angle)
        self.final_crop_box.update_image(self.rotated_grid_image)
        self.final_alignment_box.update_image(self.rotated_grid_image)
        self.alignment_grid_control.update_image(self.rotated_grid_image)

    def render_config(self):
        xpos = cwidth+10
        ypos = 10
        color = (255,255,255)


        text = font.render(f'Mode: {self.mode}', True, color)
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        text = font.render(f'Angle: {self.angle}', True, color)
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()


        ypos += 10

        for header, cb, ab, gc in [
            ('Rotation', self.crop_box, self.alignment_box, self.grid_control),
            ('Alignment', self.final_crop_box, self.final_alignment_box, self.alignment_grid_control)
            ]:

            text = font.render(header, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()
            ypos += 10

            text = f'Crop Box: {cb}'
            text = font.render(text, True, color)

            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()


            text = f'Alignment Box: {ab}'
            text = font.render(text, True, color)

            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            ypos += 10


            text = f'Gray: {gc.grayscale:0.2f}, Bright: {gc.brightness:0.2f}, Constrast: {gc.contrast:0.2f}, Sharp {gc.sharpness:0.2f}'
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            ypos += 10

            ha, va = gc.compute_angles()

            text = 'va: '+ ', '.join(f'{x:0.3f}' for x in va)
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            text = 'ha: '+ ', '.join(f'{x:0.3f}' for x in ha)
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()


            pixel_size, tile_size, grid_size = gc.compute_grid_params()

            text = f'{pixel_size=:0.2f}, {tile_size=:0.2f}, {grid_size=:0.2f}'
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            ypos += 20


    def run(self):
        cropping = False
        grid_target = (0,0)
        self.dirty = False
        while True:
            mpos = pygame.mouse.get_pos()
            keys = pygame.key.get_pressed()

            self.screen.fill((32,32,32))
            events = []
            for event in pygame.event.get():
                events.append(event)
                if event.type == QUIT:
                    pygame.quit()
                    exit()
                elif event.type == KEYDOWN:
                    if event.mod & KMOD_CTRL:
                        if event.key == K_o:
                            self.prompt_load()
                        if event.key == K_r:
                            if self.mode == 'rotate':
                                self.grid_control.init_refs()
                            elif self.mode == 'align':
                                self.alignment_grid_control.init_refs()
                    else:
                        if event.key == K_1:
                            self.mode = 'crop'
                        elif event.key == K_2:
                            self.mode = 'rotate'
                            self.grid_control.update_image()
                        elif event.key == K_3:
                            self.mode = 'final_crop'
                            self.update_aligned_image()
                        elif event.key == K_4:
                            self.mode = 'align'
                            self.update_aligned_image()

            if self.mode == 'rotate':
                for event in events:
                    if event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            if self.grid_control.finish(mpos):
                                self.dirty = True
                        elif event.button == RMB:
                            pass
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            self.grid_control.activate(mpos)
                    elif event.type == MOUSEWHEEL:
                        pass
                    elif event.type == KEYDOWN:
                        if event.mod & KMOD_CTRL:
                            if event.key == K_UP:
                                self.grid_control.do_grayscale(1); self.dirty=True
                            elif event.key == K_DOWN:
                                self.grid_control.do_grayscale(-1); self.dirty=True
                            elif event.key == K_LEFT:
                                self.grid_control.do_sharpness(-1); self.dirty=True
                            elif event.key == K_RIGHT:
                                self.grid_control.do_sharpness(1); self.dirty=True
                        else:
                            if event.key == K_UP:
                                self.grid_control.do_contrast(1); self.dirty=True
                            elif event.key == K_DOWN:
                                self.grid_control.do_contrast(-1); self.dirty=True
                            elif event.key == K_LEFT:
                                self.grid_control.do_brightness(-1); self.dirty=True
                            elif event.key == K_RIGHT:
                                self.grid_control.do_brightness(1); self.dirty=True

                self.grid_control.update(mpos)
                self.grid_control.render(screen)
            elif self.mode == 'align':
                for event in events:
                    if event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            if self.alignment_grid_control.finish(mpos):
                                self.dirty = True
                        elif event.button == RMB:
                            pass
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            self.alignment_grid_control.activate(mpos)
                    elif event.type == MOUSEWHEEL:
                        pass
                    elif event.type == KEYDOWN:
                        if event.mod & KMOD_CTRL:
                            if event.key == K_UP:
                                self.alignment_grid_control.do_grayscale(1); self.dirty=True
                            elif event.key == K_DOWN:
                                self.alignment_grid_control.do_grayscale(-1); self.dirty=True
                            elif event.key == K_LEFT:
                                self.alignment_grid_control.do_sharpness(-1); self.dirty=True
                            elif event.key == K_RIGHT:
                                self.alignment_grid_control.do_sharpness(1); self.dirty=True
                        else:
                            if event.key == K_UP:
                                self.alignment_grid_control.do_contrast(1); self.dirty=True
                            elif event.key == K_DOWN:
                                self.alignment_grid_control.do_contrast(-1); self.dirty=True
                            elif event.key == K_LEFT:
                                self.alignment_grid_control.do_brightness(-1); self.dirty=True
                            elif event.key == K_RIGHT:
                                self.alignment_grid_control.do_brightness(1); self.dirty=True

                self.alignment_grid_control.update(mpos)
                self.alignment_grid_control.render(screen)

            elif self.mode == 'crop':
                for event in events:
                    if event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            if self.alignment_box.finish(mpos):
                                self.dirty = True
                        elif event.button == LMB:
                            if self.crop_box.finish(mpos):
                                self.crop_surface = self.crop_box.get_cropped_surface()
                                self.dirty = True
                        elif event.button == RMB:
                            self.crop_box.abort()
                            self.alignment_box.abort()
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button == MMB:
                            self.alignment_box.activate(mpos)
                        elif event.button == LMB:
                            self.crop_box.activate(mpos)
                    elif event.type == MOUSEWHEEL:
                        pass

                self.crop_box.update(mpos)
                self.alignment_box.update(mpos)

                self.screen.blit(self.crop_surface, (0,0))

                if self.crop_box.active:
                    self.crop_box.render(self.screen, (255,0,255))

                grid_boxes = self.grid_control.get_boxes()

                for ul, lr in grid_boxes:
                    ul = self.alignment_box.to_screen(ul)
                    lr = self.alignment_box.to_screen(lr)

                    csize = [lr[x]-ul[x] for x in [0,1]]
                    crect = pygame.Rect(ul, csize)
                    pygame.gfxdraw.rectangle(self.screen, crect, (0,255,0))

                self.alignment_box.render(self.screen, (0,255,0))
            elif self.mode == 'final_crop':
                for event in events:
                    if event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            if self.final_alignment_box.finish(mpos):
                                self.dirty = True
                        elif event.button == LMB:
                            if self.final_crop_box.finish(mpos):
                                self.dirty = True
                        elif event.button == RMB:
                            self.final_crop_box.abort()
                            self.final_alignment_box.abort()
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button == MMB:
                            self.final_alignment_box.activate(mpos)
                        elif event.button == LMB:
                            self.final_crop_box.activate(mpos)
                    elif event.type == MOUSEWHEEL:
                        pass

                self.final_crop_box.update(mpos)
                self.final_alignment_box.update(mpos)

                self.screen.blit(self.rotated_grid_surface, (0,0))

                self.final_crop_box.render(self.screen, (255,0,255))

                grid_boxes = self.alignment_grid_control.get_boxes()

                for ul, lr in grid_boxes:
                    ul = self.final_alignment_box.to_screen(ul)
                    lr = self.final_alignment_box.to_screen(lr)

                    csize = [lr[x]-ul[x] for x in [0,1]]
                    crect = pygame.Rect(ul, csize)
                    pygame.gfxdraw.rectangle(self.screen, crect, (0,255,0))

                self.final_alignment_box.render(self.screen, (0,255,0))


            self.render_config()

            pygame.display.update()
            time.sleep(0.05)

            if self.dirty:
                self.save()


app = App(screen)

app.run()




