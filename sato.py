import os
import time
import math
import json
from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops, ImageEnhance
import numpy as np

import crossfiledialog as cfd
import platformdirs

from morphsuit import morph, gimp, ui

import pygame
import pygame.gfxdraw
import pygame.transform
from pygame.locals import *

#TODO
"""
"""

LMB = 1
MMB = 2
RMB = 3

pygame.init()
pygame.font.init()

#font = pygame.font.Font(size=24)
fontsize = 18
font = pygame.font.SysFont('monospace', size=fontsize)
bldfont = pygame.font.SysFont('monospace', size=fontsize, bold=True)

width, height = 1650,1000
GN = 3
cheight = height
cwidth = cheight

ROTATE_RESAMPLE = Image.Resampling.BICUBIC

screen=pygame.display.set_mode((width, height))

def image_to_surface(image):
    return pygame.image.fromstring(image.tobytes(), image.size, image.mode)

def surface_to_image(surface):
    return Image.frombytes("RGB", surface.get_size(),
        pygame.image.tobytes(surface, "RGB", False)
        )

app_config = ui.AppConfig('gato')

class CropBox():
    def __init__(self, base_image, int_corners = True, data = None):
        self.base_image = base_image
        self.int_corners = int_corners

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
        if self.int_corners:
            return (round(l), round(t)), (round(r), round(b))
        else:
            return (l,t),(r,b)

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
            self.grayscale = 0.1
            self.contrast = 7.2
            self.brightness = 0.6
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

    def render(self, screen, offset):
        screen.blit(self.background_surface, (0,0))

        ul = list(self.alignment_box.ul)
        lr = self.alignment_box.lr

        ul[0] += offset[0]
        ul[1] += offset[1]
        ul = tuple(ul)

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
                    round(x1), round(y1), round(x2), round(y2),
                    color)

            x,y = cmap(p, 0, i)
            pygame.gfxdraw.filled_circle(screen, round(x), round(y), 7, color)
            x,y = cmap(q, GN-1, i)
            pygame.gfxdraw.filled_circle(screen, round(x), round(y), 7, color)

    def render_crop_mode(self, screen, ref_box):
        color = (255,0,255)
        for i in range(GN):
            p,q = [ref_box.to_screen(x) for x in self.vrefs[i]]
            r,s = [ref_box.to_screen(x) for x in self.hrefs[i]]
            for x,y in [p,q,r,s]:
                pygame.gfxdraw.filled_circle(screen, round(x),round(y), 3, color)



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
                a = (a[0]-ul[0], a[1]-ul[1])
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


class SelectionBox():
    def __init__(self, options):
        self.options = options
        self.sel = 0
        self.done = False

    def render(self, screen, xpos, ypos):

        color = (225,225,225)
        selcolor = (20,20,20)
        s = 10

        width = 0
        height = 0

        text_surfaces = []

        name_width = 0
        val_width = 0

        for idx, (name, value) in enumerate(self.options):
            if idx != self.sel:
                name_text = font.render(f'{name}:  ', True, color)
                val_text = font.render(f'{value:0.3f}', True, color)
            else:
                name_text = font.render(f'{name}:  ', True, selcolor)
                val_text = font.render(f'{value:0.3f}', True, selcolor)

            name_width = max(name_width, name_text.get_width())
            val_width = max(val_width, val_text.get_width())
            height += max(name_text.get_height(), val_text.get_height())
            text_surfaces.append((name_text, val_text))

        width = name_width+val_width

        xpos -= width/2
        ypos -= height/2

        screen.fill((0,0,0), pygame.Rect(xpos-s, ypos-s, width+2*s, height+2*s))

        for idx, (name_text, val_text) in enumerate(text_surfaces):
            line_height = max(name_text.get_height(), val_text.get_height())
            if idx == self.sel:
                screen.fill(color, pygame.Rect(xpos, ypos, width, line_height))

            screen.blit(name_text, (xpos, ypos))
            screen.blit(val_text, (xpos+name_width, ypos))
            ypos += line_height

    def inc_sel(self, amount):
        self.sel+= amount
        self.sel %= len(self.options)


class App():
    def __init__(self, screen):

        self.cal_dir = 'calibrations'
        self.cal_config = os.path.join(self.cal_dir, 'slot_9.txt') #FIXME

        self.project_dir = app_config.config.get('current_project')

        if self.project_dir is None:
            self.prompt_load()
        else:
            try:
                self.load()
            except:
                self.prompt_load()

    def prompt_load(self):
        project_dir = app_config.memory_select(cfd.choose_folder)
        if project_dir is not None:
            self.project_dir = project_dir
            app_config.config['current_project'] = self.project_dir
            app_config.save()
            self.load()

    def load(self):
        self.grid_project_file = os.path.join(self.project_dir, 'gato.json')
        self.project_file = os.path.join(self.project_dir, 'sato.json')

        config = {}
        self.dirty = True
        if os.path.exists(self.project_file):
            with open(self.project_file, 'r') as fp:
                config = json.load(fp)
                self.dirty = False

        grid_config = {}
        with open(self.grid_project_file) as fp:
            grid_config = json.load(fp)

        self.screen = screen

        self.input_dir = os.path.join(self.project_dir, 'inputs')

        self.base_images = list(sorted([x for x in os.listdir(self.input_dir)]))

        self.base_images.remove('grid')
        self.base_images.insert(0,'grid')

        self.base_images = tuple(self.base_images)

        self.output_dir = os.path.join(self.project_dir, 'aligned_inputs')

        if len(self.base_images) == 0:
            raise RuntimeError('Not a valid project dir - no images in inputs')

        self.images = {}
        self.surfaces = {}
        for filename in self.base_images:
            image = Image.open(os.path.join(self.input_dir, filename))
            self.images[filename] = image
            self.surfaces[filename] = image_to_surface(image)

        self.grid_image = self.images['grid']
        self.grid_surface = image_to_surface(self.grid_image)

        self.active_image = 'grid'
        self.offsets = {x: [0,0] for x in self.base_images}
        self.offsets.update(config.get('offsets', {}))

        #Final Crop

        self.final_crop_box = CropBox(self.grid_image, True)
        self.final_crop_surface = self.final_crop_box.get_cropped_surface()

        cbox = grid_config.get('final_crop_box')
        abox = grid_config.get('final_alignment_box')

        abox['ul'][0] -= cbox['ul'][0]
        abox['ul'][1] -= cbox['ul'][1]
        abox['lr'][0] -= cbox['ul'][0]
        abox['lr'][1] -= cbox['ul'][1]


        self.final_alignment_box = CropBox(self.grid_image, False, abox)
        self.final_alignment_box.set_parent(self.final_crop_box)

        #Final Grid

        agrid = grid_config.get('alignment_grid')
        for key, ref in agrid['hrefs'].items():
            for coord in ref:
                coord[0] -= cbox['ul'][0]
                coord[1] -= cbox['ul'][1]
        for key, ref in agrid['vrefs'].items():
            for coord in ref:
                coord[0] -= cbox['ul'][0]
                coord[1] -= cbox['ul'][1]

        self.alignment_grid_control = GridControl(self.grid_image, self.final_alignment_box, self.final_crop_box, agrid)

        def align_grid_align_update():
            self.alignment_grid_control.compute_params()
        self.final_alignment_box.on_change.append(align_grid_align_update)

    def export(self):
        Image.MAX_IMAGE_PIXELS = None
        os.makedirs(self.output_dir, exist_ok = True)
        base_surface = self.screen.copy()
        pygame.gfxdraw.box(base_surface, pygame.Rect(0,0,*base_surface.get_size()), (0,0,0,128))
        for idx, infile in enumerate(self.base_images):
            inpath = os.path.join(self.input_dir, infile)
            outpath = os.path.join(self.output_dir, infile)

            self.screen.blit(base_surface, (0,0))

            text = font.render(f'{idx+1}/{len(self.base_images)}  Exporting {infile}', True, (255,255,255))
            w,h = self.screen.get_size()
            tw, th = text.get_size()
            xpos = w/2-tw/2
            ypos = h/2-th/2
            s = 20

            self.screen.fill((0,0,0), pygame.Rect(xpos-s, ypos-s, tw+s*2, th+s*2))

            self.screen.blit(text, (xpos, ypos))
            pygame.display.update()




            image = self.images[infile]

            dx, dy = self.offsets[infile]

            if dx == 0 and dy == 0:
                output_image = image
            else:
                s = 10
                w, h = image.size
                wx = w*s
                hx = h*s

                dx*=s
                dy*=s
                dx = round(dx)
                dy = round(dy)

                image = image.resize((wx, hx))

                crop = [0,0]
                box = [0,0]
                if dx > 0:
                    box[0] = dx
                else:
                    crop[0] = -dx
                if dy > 1:
                    box[1] = dy
                else:
                    crop[1] = -dy

                output_image = Image.new('RGB', (wx, hx))

                if crop[0] != 0 or crop[1] != 0:
                    image = image.crop([*crop, *image.size])

                output_image.paste(image, box)
                output_image = output_image.resize((w,h))

            output_image.save(outpath, format='png')

            stop = False
            for event in pygame.event.get():
                 if event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        stop = True
            if stop: break


    def save(self):
        data = {
            'offsets': self.offsets
            }
        with open(self.project_file, 'w') as fp:
            json.dump(data, fp, indent = 2)
        self.dirty = False

    def render_config(self):
        xpos = cwidth+10
        ypos = 10
        color = (255,255,255)

        text = font.render(f'Hello', True, color)
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        width = 0
        for name in self.base_images:
            color = (255,255,255)
            if name == self.active_image:
                color = (0,255,0)
            text = font.render(name, True, color)
            width = max(width, text.get_width())

        for name in self.base_images:
            color = (255,255,255)
            if name == self.active_image:
                color = (0,255,0)
            text = font.render(name, True, color)
            self.screen.blit(text, (xpos, ypos))
            h = text.get_height()

            dx, dy = self.offsets[name]
            text = font.render(f'{dx:.2f}, {dy:.2f}', True, color)
            self.screen.blit(text, (xpos+width+10, ypos))
            h = max(h, text.get_height())

            ypos += h


        ypos += 10

    def inc_active_image(self, amt):
        idx = self.base_images.index(self.active_image)
        idx += amt
        if idx < 0: idx += len(self.base_images)
        if idx >= len(self.base_images): idx -= len(self.base_images)

        self.active_image = self.base_images[idx]
        self.alignment_grid_control.update_image(self.images[self.active_image])

    def get_relative_offset(self, mpos):
        offset = list(self.offsets[self.active_image])
        if self.dragging:
            dx = mpos[0]-self.start_pos[0]
            dy = mpos[1]-self.start_pos[1]
            offset[0] -= dx/10
            offset[1] -= dy/10
        return offset


    def run(self):
        self.dirty = False
        self.dragging = False
        self.start_pos = None
        while True:
            mpos = pygame.mouse.get_pos()
            keys = pygame.key.get_pressed()

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
                        elif event.key == K_e:
                            self.export()
                    else:
                        if event.key == K_1:
                            pass

            self.screen.fill((32,32,32))

            for event in events:
                if event.type == MOUSEBUTTONUP:
                    if event.button == MMB:
                        pass
                    elif event.button == LMB:
                        if self.dragging:
                            self.offsets[self.active_image] = self.get_relative_offset(mpos)
                            self.dragging = False
                            self.dirty=True
                    elif event.button == RMB:
                        pass
                elif event.type == MOUSEBUTTONDOWN:
                    if event.button == MMB:
                        pass
                    elif event.button == LMB:
                        if self.active_image != 'grid':
                            self.dragging = True
                            self.start_pos = mpos
                elif event.type == MOUSEWHEEL:
                    pass
                elif event.type == KEYDOWN:
                    if event.key == K_UP:
                        self.inc_active_image(-1)
                    elif event.key == K_DOWN:
                        self.inc_active_image(1)
                    elif event.key == K_LEFT:
                        pass
                    elif event.key == K_RIGHT:
                        pass

            offset = self.get_relative_offset(mpos)

            self.alignment_grid_control.render(screen, offset)


            self.render_config()

            pygame.display.update()
            time.sleep(0.05)

            if self.dirty:
                self.save()


app = App(screen)

app.run()




