import os
import time
import math
import json
from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops

import cv2

import crossfiledialog as cfd

from morphsuit import morph, gimp, ui

import pygame
import pygame.gfxdraw
import pygame.transform
from pygame.locals import *

#TODO
"""
Update Gimp to use gato file for grid alignment instead of layers
Update Gimp to use contours for masking and cropping sprites instead of layers
    if multiple segments have the same label, then merge them
    Probably pre-generate mask images for masking with same size as cropping bounds
    crop, then mask cropped image
    pillow transform module for subpixel cropping?
"""

LMB = 1
MMB = 2
RMB = 3

width, height = 1650,1000
cheight = height
cwidth = cheight

pygame.init()
pygame.font.init()

#font = pygame.font.Font(size=24)
fontsize = 18
font = pygame.font.SysFont('monospace', size=fontsize)
bldfont = pygame.font.SysFont('monospace', size=fontsize, bold=True)

app_config = ui.AppConfig('gato')

def image_to_surface(image):
    return pygame.image.fromstring(image.tobytes(), image.size, image.mode)

def surface_to_image(surface):
    return Image.frombytes("RGB", surface.get_size(),
        pygame.image.tobytes(surface, "RGB", False)
        )

class TextControl():
    def __init__(self, text = None, parent = None):
        self.text = text
        self.parent = parent

    def key(self, event):
        if event.key == K_BACKSPACE:
            return self.backspace()
        elif event.key == K_DELETE:
            return False
        else:
            return self.type(event.unicode)

    def backspace(self):
        if self.text is None: return False

        self.text = self.text[:-1]
        if self.text == "":
            self.text = None
        return True

    def type(self, char):
        if char in {' ', '\n', '\r'}: return False

        if self.text is None:
            self.text = ""
        self.text += char
        return True

class TextBox():
    def __init__(self, xpos, ypos, name, text=None):
        self.xpos = xpos
        self.ypos = ypos
        self.name = name
        self.text = TextControl(text, self)
        self.get_text_image((0,0,0))

    def get_text_image(self, color):
        text = self.name+': '
        if self.text.text is not None:
            text += self.text.text
        text = font.render(text, True, color)
        self.width, self.height = text.get_size()
        return text

    def get_hit(self, pos):
        return (pos[0] > self.xpos and pos[0] < self.xpos+self.width and
                pos[1] > self.ypos and pos[1] < self.ypos+self.height)

    def render(self, screen, color):
        text = self.get_text_image(color)
        screen.blit(text, (self.xpos, self.ypos))

class Contour():
    def __init__(self, contour, point = None, label = None):
        self.contour = contour
        self.point = point
        self.label = TextControl(label, self)

    def get_hit(self, pos):
        return cv2.pointPolygonTest(self.contour, pos, False) > 0

    def render(self, screen, scale, selected, prefix):
        x,y,w,h = [a*scale for a in cv2.boundingRect(self.contour)]

        color = (0,255,0)
        if self.point is None or self.label.text is None:
            color = (255,0,0)

        if selected:
            color = (255,0,255)

        pygame.gfxdraw.rectangle(screen, pygame.Rect(x,y,w,h), color)

        if selected:
            points = [[round(y*scale) for y in x[0]] for x in self.contour]
            pygame.gfxdraw.aapolygon(screen, points, (0,0,255))

        if self.point is not None:
            xp,yp = [a*scale for a in self.point]
            pygame.gfxdraw.filled_circle(screen, round(xp),round(yp), 5, color)

        if self.label.text is not None:
            text = self.label.text
            if prefix is not None:
                text = prefix+text
            text = font.render(text, True, color)
            screen.blit(text, (round(x+3), round(y+3)))



class App():

    def __init__(self):
        self.project_dir = app_config.config.get('current_project')

        if self.project_dir is None:
            self.prompt()

        self.screen=pygame.display.set_mode((width, height))

        self.load()

    def prompt(self):
        project_dir = app_config.memory_select(cfd.choose_folder)
        if project_dir is not None:
            self.project_dir = project_dir
        else:
            raise RuntimeError('Pick a project')

    def prompt_load(self):
        try:
            self.prompt()
        except RuntimeError:
            return

        self.load()


    def load(self):
        self.project = gimp.GimpProject(os.path.join(self.project_dir, 'inputs.xcf'), 'output')
        #project.export_layers()
        #project.export_layers('sprites')

        self.config_file = os.path.join(self.project_dir, 'segs.json')
        self.dirty = True
        config = {}
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as fp:
                config = json.load(fp)
                self.dirty = False

        self.padding = config.get('padding', 10)

        self.base_image = self.project.layers['sprites'].image
#        self.base_image = self.project.get_expanded_layer('sprites', self.padding)
        self.base_surface = image_to_surface(self.base_image)

        w,h = self.base_surface.get_size()

        self.scale = min(cwidth/w, cheight/h)
        self.bg_surface = pygame.transform.scale_by(self.base_surface, self.scale)

        self.text_boxes = []

        xpos = cwidth+10
        ypos = 10

        self.auto_prefix_box = TextBox(xpos, ypos, 'Auto Prefix', config.get('auto_prefix'))
        self.text_boxes.append(self.auto_prefix_box)

        self.prefix_box = TextBox(xpos, ypos, 'Prefix', config.get('prefix'))
        self.text_boxes.append(self.prefix_box)



        self.recompute_contours(config.get('labels', []))

        self.selection = None

    def recompute_contours(self, labels=None):
        if labels is None:
            labels = self.extract_labels()

        self.contours = self.project.get_layer_segments('sprites', self.padding)
        self.contours = [Contour(x) for x in self.contours]

        for label, point in labels:
            for cnt in self.contours:
                if cnt.get_hit(point):
                    cnt.point = point
                    cnt.label.text = label

    def extract_labels(self):
        labels = []
        for cnt in self.contours:
            if cnt.point is None or cnt.label.text is None:
                continue
            text = cnt.label.text
            labels.append((text, cnt.point))
        return labels

    def count_labels(self):
        counts = defaultdict(lambda:0)
        for cnt in self.contours:
            if cnt.point is None or cnt.label.text is None:
                continue
            text = cnt.label.text
            counts[text] += 1
        counts = list(sorted(counts.items(), key = lambda x: (x[1], x[0]), reverse=True))
        return counts

    def count_unlabeled(self):
        result = 0
        for cnt in self.contours:
            if cnt.point is None or cnt.label.text is None:
                result += 1
        return result

    def save(self):
        config = {
            'padding': self.padding,
            'labels': self.extract_labels(),
            'prefix': self.prefix_box.text.text or '',
            'auto_prefix': self.auto_prefix_box.text.text or '',
            }

        with open(self.config_file, 'w') as fp:
            json.dump(config, fp, indent=2)

        self.dirty = False

    auto_inc_suffix = ','

    def get_auto_index(self, inc = False):
        value = 0
        width = self.auto_label_width()

        auto_prefix = self.auto_prefix_box.text.text or ''

        is_zero = True
        for cnt in self.contours:
            if cnt.label.text is not None:
                if not cnt.label.text.startswith(auto_prefix): continue
                try:
                    value = max(value, int(cnt.label.text[len(auto_prefix):len(auto_prefix)+width]))
                    is_zero = False
                except ValueError:
                    pass
        if is_zero: return 0
        if inc:
            return value + 1
        return value

    def auto_label_width(self):
        return len(str(len(self.contours)-1))

    def index_to_label(self, idx):
        digits = self.auto_label_width()
        auto_prefix = self.auto_prefix_box.text.text or ''
        return auto_prefix+str(idx).zfill(digits)+self.auto_inc_suffix

    def image_to_screen(self, pos):
        return tuple(x*self.scale for x in pos)

    def screen_to_image(self, pos):
        return tuple(x/self.scale for x in pos)

    def select_contour(self, mpos, auto_label, auto_inc):
        pos = self.screen_to_image(mpos)

        self.selection = None
        for cnt in self.contours:
            if cnt.get_hit(pos):
                if cnt.label.text is None and auto_label:
                    idx = self.get_auto_index(auto_inc)
                    cnt.label.text = self.index_to_label(idx)

                self.selection = cnt.label
                cnt.point = pos
                self.dirty = True
                return True
        return False

    def inc_padding(self, amt):
        self.padding += amt
        self.padding = max(self.padding, 0)
        self.recompute_contours()
        self.dirty = True

    def render_config(self):
        xpos = cwidth+10
        ypos = 10
        color = (255,255,255)


        text = ' '
        if self.dirty:
            text = 'Unsaved'
        text = font.render(text, True, (255,255,0))
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        ypos += 10

        text = font.render(f'Segments: {len(self.contours)}', True, (255,255,255))
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        text = font.render(f'Padding: {self.padding}', True, (255,255,255))
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        ypos += 10

        idx = self.get_auto_index()
        text = self.index_to_label(idx)
        text = font.render(f'Current auto label: {text}', True, (255,255,255))
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        for box in self.text_boxes:
            box.ypos = ypos
            box.xpos = xpos
            color = (0,255,0)
            if self.selection is box.text:
                color = (255,0,255)
            box.render(self.screen, color)
            ypos += box.height

        ypos += 10

        count = self.count_unlabeled()
        text = font.render(f'Unlabeled: {count}', True, (255,255,255))
        self.screen.blit(text, (xpos, ypos))
        ypos += text.get_height()

        ypos += 10

        labels = self.count_labels()
        for label, count in labels:
            text = label
            if self.prefix_box.text.text is not None:
                text = self.prefix_box.text.text+label
            text = font.render(f'{count}: {text}', True, (255,255,255))
            self.screen.blit(text, (xpos, ypos))
            ypos += text.get_height()




    def run(self):
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
                if event.type == MOUSEBUTTONUP:
                    if event.button == MMB:
                        pass
                    elif event.button == LMB:
                        pass
                    elif event.button == RMB:
                        pass
                elif event.type == MOUSEBUTTONDOWN:
                    if event.button == MMB:
                        pass
                    elif event.button == LMB:
                        for box in self.text_boxes:
                            if box.get_hit(mpos):
                                self.selection = box.text
                                break
                        else:
                            self.select_contour(mpos, not mods & KMOD_CTRL, not mods & KMOD_SHIFT)
                elif event.type == KEYDOWN:
                    if event.mod & KMOD_CTRL:
                        if event.key == K_o:
                            self.prompt_load()
                        elif event.key == K_s:
                            self.save()
                    elif event.key == K_UP:
                        self.inc_padding(1)
                    elif event.key == K_DOWN:
                        self.inc_padding(-1)
                    elif self.selection is not None:
                        if self.selection.key(event):
                            self.dirty = True

                        if self.selection.parent is not None:
                            if event.key == K_DELETE:
                                self.selection.parent.point = None
                                self.dirty = True


            self.screen.fill( (64,64,64) )

            self.screen.blit(self.bg_surface, (0,0))

            for cnt in self.contours:
                is_sel = self.selection is not None and cnt is self.selection.parent
                cnt.render(self.screen, self.scale, is_sel, self.prefix_box.text.text)

            self.render_config()

            pygame.display.update()
            time.sleep(0.05)


app = App()

app.run()



exit(0)

image = Image.open('rect_test/sprites.png')

image = gimp.pil_to_cv(image)

_,_,_,alpha = cv2.split(image)

ret, thresh = cv2.threshold(alpha, 127,255,0)
contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

test_point = (200,1800)
image = cv2.circle(image, test_point, 5, (0,0,255,255), 2)

for cnt in contours:
    x,y,w,h = cv2.boundingRect(cnt)
    print(x,y,w,h)
    color = (0,255,0,255)
    if cv2.pointPolygonTest(cnt, test_point, False) > 0:
        color = (0,0,255,255)

    m = cv2.moments(cnt)
    if m['m00'] == 0: continue

    cx = m['m10']/m['m00']
    cy = m['m01']/m['m00']

    image = cv2.circle(image, (int(cx), int(cy)), 5, color, 2)

    image = cv2.rectangle(image, (x,y), (x+w, y+h), color, 2)

image = gimp.cv_to_pil(image)

image.show()


"""
mask = Image.open('rect_test/sprites.png')

mask = gimp.pil_to_cv(image)

w,h,c = mask.shape

image = np.zeros(shape=(w-2, h-2, c))
"""

