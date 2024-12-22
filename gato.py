import os
import time
import math
from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops, ImageEnhance

from morphsuit import morph, gimp

import pygame
import pygame.gfxdraw
import pygame.transform
from pygame.locals import *

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

class CropBox():
    def __init__(self, base_image, ul = None, lr = None):
        self.base_image = base_image
        self.ul = ul or (0,0)
        self.lr = lr or base_image.size
        self.update_params()
        self.active = False
        self.eul = None
        self.elr = None
        self.parent = None

        self.on_change = []

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

    def activate(self, mpos):
        if self.active: return
        self.active = True
        self.eul = self.from_screen(mpos)
        self.elr = self.eul

    def abort(self):
        self.active = False

    def update(self, mpos):
        if not self.active: return
        self.elr = self.from_screen(mpos)

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
    def __init__(self, base_image, alignment_box):
        self.base_image = base_image
        self.alignment_box = alignment_box

        self.active = False
        self.sel_idx = 0
        self.sel_ref = None

        self.compute_params()
        self.init_refs()


        self.grayscale = 1
        self.contrast = 1
        self.brightness = 1
        self.sharpness = 1

        self.background_surface_raw = self.render_base()
        self.background_surface = self.apply_contrast()

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

        #TODO load from file
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

        self.giw = giw = 200
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
        if not self.active: return
        self.active = False


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


    def compute_grid_params(self):

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


        """
        if self.grid_refs is not None:

            va = []
            ha = []
            for i in range(GN):
                t = self.grid_refs[(i,0)]
                b = self.grid_refs[(i,GN-1)]
                va.append(get_angle(t,b))

                l = self.grid_refs[(0,i)]
                r = self.grid_refs[(GN-1, i)]
                ha.append(get_angle(l, r))

            text = 'va: '+ ', '.join(f'{x:0.3f}' for x in va)
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            text = 'ha: '+ ', '.join(f'{x:0.3f}' for x in ha)
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            ul = self.grid_refs[(0,0)]
            lr = self.grid_refs[(GN-1, GN-1)]
            w = lr[0]-ul[0]
            h = lr[1]-ul[1]
            guess = 52.7
            gx = round(w/guess)
            gy = round(h/guess)
            pixel_size = (w**2+h**2)**0.5
            tile_size = (gx**2+gy**2)**0.5
            grid_size = pixel_size/tile_size

            text = f'{pixel_size=:0.2f}, {tile_size=:0.2f}'
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            text = f'{gx=}, {gy=}, {grid_size=:0.2f}'
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()
        """





class App():
    def __init__(self, screen):
        self.cal_dir = 'calibrations'

        self.project_dir = 'rect_test' #FIXME
        self.cal_config = os.path.join(self.cal_dir, 'slot_9.txt') #FIXME

        self.screen = screen

        self.raw_dir = os.path.join(self.project_dir, 'raw_inputs')
        self.raw_images = [x for x in os.listdir(self.raw_dir) if x.endswith('.jpg')]

        self.morpher = morph.MorphProject(self.cal_config)

        self.grid_file = os.path.join(self.raw_dir, 'grid.jpg')
        self.grid_image = Image.open(self.grid_file)
        self.grid_image = self.morpher.lens_correct(self.grid_image)
        self.grid_surface = image_to_surface(self.grid_image)


        self.mode = 'crop'
#        self.crop_box = CropBox(self.grid_image)
        self.crop_box = CropBox(self.grid_image, (554.69,599.18), (2312.35,2895.41))#FIXME
        self.crop_surface = self.crop_box.get_cropped_surface()

#        self.alignment_box = CropBox(self.grid_image)
        self.alignment_box = CropBox(self.grid_image, (621.28,654.29), (2233.23,2812.75))
        self.alignment_box.set_parent(self.crop_box)

        def align_update():
            self.alignment_box.crop_to_parent()
        self.crop_box.on_change.append(align_update)

        self.mode = 'rotate'
        self.grid_refs = None
        self.grid_control = GridControl(self.grid_image, self.alignment_box)

        def grid_align_update():
            self.grid_control.compute_params()
        self.alignment_box.on_change.append(grid_align_update)

    def render_config(self):
        xpos = cwidth+10
        ypos = 10
        color = (255,255,255)

        text = f'Crop Box: {self.crop_box}'
        text = font.render(text, True, color)

        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()


        text = f'Alignment Box: {self.alignment_box}'
        text = font.render(text, True, color)

        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()


        ypos += 10

        text = f'Gray: {self.grid_control.grayscale:0.2f}, Bright: {self.grid_control.brightness:0.2f}, Constrast: {self.grid_control.contrast:0.2f}, Sharp {self.grid_control.sharpness:0.2f}'
        text = font.render(text, True, color)
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        ypos += 10


        def get_angle(a,b):
            dx = a[0]-b[0]
            dy = a[1]-b[1]
            res = math.atan2(dy, dx)*180/math.pi
            res -= round(res/90)*90
            return res

        if self.grid_refs is not None:

            va = []
            ha = []
            for i in range(GN):
                t = self.grid_refs[(i,0)]
                b = self.grid_refs[(i,GN-1)]
                va.append(get_angle(t,b))

                l = self.grid_refs[(0,i)]
                r = self.grid_refs[(GN-1, i)]
                ha.append(get_angle(l, r))

            text = 'va: '+ ', '.join(f'{x:0.3f}' for x in va)
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            text = 'ha: '+ ', '.join(f'{x:0.3f}' for x in ha)
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            ul = self.grid_refs[(0,0)]
            lr = self.grid_refs[(GN-1, GN-1)]
            w = lr[0]-ul[0]
            h = lr[1]-ul[1]
            guess = 52.7
            gx = round(w/guess)
            gy = round(h/guess)
            pixel_size = (w**2+h**2)**0.5
            tile_size = (gx**2+gy**2)**0.5
            grid_size = pixel_size/tile_size

            text = f'{pixel_size=:0.2f}, {tile_size=:0.2f}'
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

            text = f'{gx=}, {gy=}, {grid_size=:0.2f}'
            text = font.render(text, True, color)
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()




    def run(self):
        cropping = False
        grid_target = (0,0)
        while True:
            mpos = pygame.mouse.get_pos()
            keys = pygame.key.get_pressed()

            self.screen.fill((32,32,32))

            if self.mode == 'rotate':
                for event in pygame.event.get():
                    if event.type == QUIT:
                        pygame.quit()
                        exit()
                    elif event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            self.grid_control.finish(mpos)
                            pass
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
                                self.grid_control.do_grayscale(1)
                            elif event.key == K_DOWN:
                                self.grid_control.do_grayscale(-1)
                            elif event.key == K_LEFT:
                                self.grid_control.do_sharpness(-1)
                            elif event.key == K_RIGHT:
                                self.grid_control.do_sharpness(1)
                        else:
                            if event.key == K_UP:
                                self.grid_control.do_contrast(1)
                            elif event.key == K_DOWN:
                                self.grid_control.do_contrast(-1)
                            elif event.key == K_LEFT:
                                self.grid_control.do_brightness(-1)
                            elif event.key == K_RIGHT:
                                self.grid_control.do_brightness(1)

                self.grid_control.update(mpos)
                self.grid_control.render(screen)



            if self.mode == 'crop':
                for event in pygame.event.get():
                    if event.type == QUIT:
                        pygame.quit()
                        exit()
                    elif event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            self.alignment_box.finish(mpos)
                        elif event.button == LMB:
                            if self.crop_box.finish(mpos):
                                self.crop_surface = self.crop_box.get_cropped_surface()
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

                self.alignment_box.render(self.screen, (0,255,0))

            self.render_config()

            pygame.display.update()
            time.sleep(0.05)


app = App(screen)

app.run()




