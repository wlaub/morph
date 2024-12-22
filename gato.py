import os
import time
import math
from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops

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
        self.alignment_box = CropBox(self.grid_image)
        self.alignment_box.set_parent(self.crop_box)

#        self.mode = 'rotate'
        self.grid_refs = None

    def render_config(self):
        xpos = cwidth+10
        ypos = 10
        color = (255,255,255)

        if self.crop_box is not None:
            text = f'Crop Box: {self.crop_box}'
            text = font.render(text, True, color)

            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()

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
        gridding = False
        grid_target = (0,0)
        while True:
            mpos = pygame.mouse.get_pos()
            keys = pygame.key.get_pressed()

            if self.mode == 'rotate':
                ul = self.crop_box[0]
                lr = self.crop_box[1]

                csize = [lr[x]-ul[x] for x in [0,1]]

                gbw = cwidth/GN
                gbh = cheight/GN

                giw = 200
                gih = giw*gbh/gbw

                dx = (csize[0]-giw)/(GN-1)
                dy = (csize[1]-gih)/(GN-1)

                for event in pygame.event.get():
                    if event.type == QUIT:
                        pygame.quit()
                        exit()
                    elif event.type == MOUSEBUTTONUP:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            gridding = False
                            pass
                        elif event.button == RMB:
                            pass
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button == MMB:
                            pass
                        elif event.button == LMB:
                            if mpos[0] > cwidth or mpos[1] > cheight:
                                continue
                            xidx = int(mpos[0]/gbw)
                            yidx = int(mpos[1]/gbh)
                            grid_target = (xidx, yidx)
                            gridding = True
                    elif event.type == MOUSEWHEEL:
                        pass

                if gridding:
                    xidx = int(mpos[0]/gbw)
                    yidx = int(mpos[1]/gbh)
                    if (xidx, yidx) == grid_target:
                        xa = mpos[0]/gbw - xidx
                        ya = mpos[1]/gbh - yidx
                        self.grid_refs[grid_target] = (
                            ul[0] + xa*giw + xidx*dx,
                            ul[1] + ya*gih + yidx*dy
                            )

                self.screen.fill((32,32,32))

                gridded_surface = self.grid_surface.copy()

                if self.grid_refs == None:
                    self.grid_refs = {}
                    for x in range(GN):
                        for y in range(GN):
                            key = (x,y)
                            self.grid_refs[key] = (
                                ul[0]+x*dx+giw/2, ul[1]+y*dy+gih/2)

                for i in range(GN):
                    t = self.grid_refs[(i,0)]
                    b = self.grid_refs[(i,GN-1)]
                    l = self.grid_refs[(0,i)]
                    r = self.grid_refs[(GN-1, i)]
                    pygame.gfxdraw.line(gridded_surface,
                        int(t[0]), int(t[1]),
                        int(b[0]), int(b[1]),
                        (255,0,255),
                        )
                    pygame.gfxdraw.line(gridded_surface,
                        int(l[0]), int(l[1]),
                        int(r[0]), int(r[1]),
                        (255,0,255),
                        )



                target = pygame.Surface((giw*GN, gih*GN))

                for x in range(GN):
                    for y in range(GN):
                        xpos = ul[0] + x*dx
                        ypos = ul[1] + y*dy
                        target.blit(gridded_surface, (int(x*giw), int(y*gih)),
                            pygame.Rect(int(xpos), int(ypos), int(giw), int(gih))
                            )

                sf = gbw/giw
                target = pygame.transform.scale_by(target, sf)

                self.screen.blit(target, (0,0))



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
                                self.alignment_box.crop_to_parent()
                        elif event.button == RMB:
                            self.crop_box.abort()
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button == MMB:
                            self.alignment_box.activate(mpos)
                        elif event.button == LMB:
                            self.crop_box.activate(mpos)
                    elif event.type == MOUSEWHEEL:
                        pass

                self.crop_box.update(mpos)
                self.alignment_box.update(mpos)

                self.screen.fill((32,32,32))

                self.screen.blit(self.crop_surface, (0,0))

                if self.crop_box.active:
                    self.crop_box.render(self.screen, (255,0,255))

                self.alignment_box.render(self.screen, (0,255,0))

            self.render_config()

            pygame.display.update()
            time.sleep(0.05)


app = App(screen)

app.run()




