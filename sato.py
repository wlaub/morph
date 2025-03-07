import os
import time
import math
import json
from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops, ImageEnhance, ImageOps
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

class AlignmentControl():
    def __init__(self, base_image, target_image):
        self.base_image = base_image

        self.normal = False
        self.other = False

        self.image_size = 200
        self.render_size = 1000
        self.margin = 100
        self.scale = s = self.render_size/self.image_size

        self.xoff = 0
        self.yoff = 0

        self.color_scale = 1
        self.color_offset = 0

        w,h = base_image.size
        self.scaled_image = base_image.resize((round(w*s), round(h*s)))
        self.set_target_image(target_image)

    def set_target_image(self, target_image):
        s = self.scale
        w, h = target_image.size
        self.target_image_base = target_image

        self.target_image = target_image.resize((round(w*s), round(h*s)))

    def adjust_offset(self, offset):
        xoff = self.xoff+offset[0]
        yoff = self.yoff+offset[1]
        xoff = min(self.margin, max(xoff, -self.margin))
        yoff = min(self.margin, max(yoff, -self.margin))
        self.xoff = xoff
        self.yoff = yoff

    def update_color_scale(self, amt):
        self.color_scale += amt*0.1
        if self.color_scale <= 0:
            self.color_scale = 0.1

    def update_color_offset(self, amt):
        self.color_offset += amt*3

    def make_render_image(self, offset, temp_offset):
        s = self.scale
        w,h = self.scaled_image.size

        xoff = self.xoff+temp_offset[0]
        yoff = self.yoff+temp_offset[1]
        xoff = min(self.margin, max(xoff, -self.margin))
        yoff = min(self.margin, max(yoff, -self.margin))

        x = w/2-self.render_size/2+(xoff)*s
        y = h/2-self.render_size/2+(yoff)*s

        base_image = self.scaled_image.crop([x, y, x+self.render_size, y+self.render_size])
        if self.normal:
            return base_image

        x += offset[0]*self.scale
        y += offset[1]*self.scale
        x = round(x)
        y = round(y)
        other_image = self.target_image.crop([x, y, x+self.render_size, y+self.render_size])

        if self.other:
            return other_image

#        base_image = ImageOps.invert(base_image)

        result = ImageChops.subtract(other_image, base_image, scale=1/self.color_scale, offset=self.color_offset)

        return result

    def find_best_offset(self, offset):
        scale = 20
        iscale = 0.05

        scale = self.scale
        iscale = 1/self.scale

        r = math.ceil(2*scale)
        best = 0
        best_offset = None
#        print(r, r/self.scale)

#        print(f'{offset[0]-r*iscale} to {offset[0]+(r-1)*iscale}')
#        print(f'{offset[1]-r*iscale} to {offset[1]+(r-1)*iscale}')
        for dx in range(-r, r):
            for dy in range(-r,r):
                toffset = [offset[0] + dx*iscale, offset[1] + dy*iscale]
                image = self.make_render_image(toffset, [0,0])
                data = np.array(image)

                value = data.sum()
#                print(toffset)
                if 1/value > best:
                    print(value, toffset)
                    best = 1/value
                    best_offset = toffset
        return best, best_offset


    def render(self, screen, offset, temp_offset):
        image = self.make_render_image(offset, temp_offset)
        surface = image_to_surface(image)
        screen.blit(surface, (0,0))


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
        self.project_file = os.path.join(self.project_dir, 'sato.json')

        config = {}
        self.dirty = True
        if os.path.exists(self.project_file):
            with open(self.project_file, 'r') as fp:
                config = json.load(fp)
                self.dirty = False

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

        # Align control

        self.alignment_control = None
        self.inc_active_image(1)
        self.alignment_control = AlignmentControl(self.grid_image, self.images[self.active_image])

    def export(self):
        Image.MAX_IMAGE_PIXELS = None
        os.makedirs(self.output_dir, exist_ok = True)
        base_surface = self.screen.copy()
        pygame.gfxdraw.box(base_surface, pygame.Rect(0,0,*base_surface.get_size()), (0,0,0,128))
        s = self.alignment_control.scale

        for idx, infile in enumerate(self.base_images):
            inpath = os.path.join(self.input_dir, infile)
            outpath = os.path.join(self.output_dir, infile)

            self.screen.blit(base_surface, (0,0))

            text = font.render(f'{idx+1}/{len(self.base_images)}  Exporting {infile}', True, (255,255,255))
            w,h = self.screen.get_size()
            tw, th = text.get_size()
            xpos = w/2-tw/2
            ypos = h/2-th/2

            self.screen.fill((0,0,0), pygame.Rect(xpos-s, ypos-s, tw+s*2, th+s*2))

            self.screen.blit(text, (xpos, ypos))
            pygame.display.update()


            image = self.images[infile]

            dx, dy = self.offsets[infile]
            dx = -dx
            dy = -dy

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

                output_image = Image.new('RGBA', (wx, hx), (255,255,255, 0))

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

        text = font.render(f'Scale: {self.alignment_control.color_scale:0.2f}', True, color)
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        text = font.render(f'Offset: {self.alignment_control.color_offset:0.2f}', True, color)
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
        if self.alignment_control is not None:
            self.alignment_control.set_target_image(self.images[self.active_image])

    def get_relative_offset(self, mpos):
        offset = list(self.offsets[self.active_image])
        if self.dragging:
            dx = mpos[0]-self.start_pos[0]
            dy = mpos[1]-self.start_pos[1]
            offset[0] -= dx/20
            offset[1] -= dy/20
        return offset

    def get_temp_offset(self, mpos):
        if self.dragging_view:
            dx = mpos[0]-self.start_pos_view[0]
            dy = mpos[1]-self.start_pos_view[1]
            return [-dx/2, -dy/2]
        else:
            return [0,0]

    def run(self):
        self.dirty = False
        self.dragging = False
        self.start_pos = None
        self.dragging_view = False
        self.start_pos_view = None
        while True:
            mpos = pygame.mouse.get_pos()
            keys = pygame.key.get_pressed()
            mods = pygame.key.get_mods()

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
                        dx, dy = self.get_temp_offset(mpos)
                        self.alignment_control.adjust_offset((dx, dy))
                        self.dragging_view = False
                    elif event.button == LMB:
                        if self.dragging:
                            self.offsets[self.active_image] = self.get_relative_offset(mpos)
                            self.dragging = False
                            self.dirty=True
                    elif event.button == RMB:
                        pass
                elif event.type == MOUSEBUTTONDOWN:
                    if event.button == MMB:
                        self.dragging_view = True
                        self.start_pos_view = mpos
                    elif event.button == LMB:
                        if self.active_image != 'grid':
                            self.dragging = True
                            self.start_pos = mpos
                elif event.type == MOUSEWHEEL:
                    if mods & KMOD_SHIFT:
                        self.alignment_control.update_color_offset(event.y)
                    else:
                        self.alignment_control.update_color_scale(event.y)
                elif event.type == KEYDOWN:
                    if event.key == K_UP:
                        self.inc_active_image(-1)
                    elif event.key == K_DOWN:
                        self.inc_active_image(1)
                    elif event.key == K_LEFT:
                        pass
                    elif event.key == K_RIGHT:
                        pass
                    elif event.key == K_ESCAPE:
                        self.dragging = False
                    elif event.key == K_1:
                        self.alignment_control.normal = False
                        self.alignment_control.other = False
                    elif event.key == K_2:
                        self.alignment_control.normal = True
                        self.alignment_control.other = False
                    elif event.key == K_3:
                        self.alignment_control.normal = False
                        self.alignment_control.other = True
                    elif event.key == K_z:
                        self.best, self.best_offset = self.alignment_control.find_best_offset(offset)
                        self.offsets[self.active_image] = self.best_offset
                        print(self.best, self.best_offset)
                    elif event.key == K_x:
                        self.offsets[self.active_image] = self.best_offset




            offset = self.get_relative_offset(mpos)

            self.alignment_control.render(screen, offset, self.get_temp_offset(mpos))


            self.render_config()

            pygame.display.update()
            time.sleep(0.05)

            if self.dirty:
                self.save()


app = App(screen)

app.run()




