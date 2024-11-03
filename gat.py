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

class DraggablePoint():
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.active = False

    def set_pos(self, mpos):
        self.x = mpos[0]-10
        self.y = mpos[1]

    def start_drag(self, mpos, grid_size):
        if self.active:
            return False

        dist = (mpos[0]-self.x)**2 + (mpos[1]-self.y)**2
        if dist > grid_size*grid_size/9:
            return False

        self.set_pos(mpos)

        self.active = True
        return True

    def stop_drag(self, mpos):
        if not self.active:
            return

        self.set_pos(mpos)
        self.active = False

    def update_drag(self, mpos):
        if self.active:
            self.set_pos(mpos)


    def render(self, screen, mpos, offset, zoom, radius):
        x = self.x
        y = self.y
        pygame.gfxdraw.filled_circle(screen,
            round(offset[0]+x*zoom), round(offset[1]+y*zoom),
            radius,(255,0,255, 255))



project = gimp.GimpProject('inputs.xcf', 'output')

pygame.init()

grid_image = project.layers['grid'].image
pg_grid_image_base = pygame.image.fromstring(grid_image.tobytes(), grid_image.size, grid_image.mode)

wimage, himage = pg_grid_image_base.get_size()

width, height = 1500,1000
screen=pygame.display.set_mode((width, height))

zoom = 4
offset = [0,0]

pixel_size, tile_size = project._get_export_sizes(None, None)
grid_size = pixel_size/tile_size
ingame_pixel_size = grid_size/8

grid_offset = project.get_grid_offset('r')

extra_points = [[y*tile_size*8/pixel_size for y in x]for x in project.variables['r']]
extra_points = [tuple(y*ingame_pixel_size for y in x) for x in extra_points]
magic_points = [DraggablePoint(*x) for x in extra_points]

project.expand_layers('sprites', 10)

sprite_boxes = []
for layer in project.groups['sprites']:
    bbox = project._get_layer_bbox(project.layers[layer])
    bbox = project.expand_bbox_to_tiles(bbox, grid_offset, pixel_size, tile_size)
    sprite_boxes.append(bbox)


pg_grid_image = pygame.transform.scale_by(pg_grid_image_base, zoom)

def clamp_offset(x):
    result = list(x)
    if x[0] > 0:
        result[0] = 0
    if x[1] > 0:
        result[1] = 0
    if x[0] < -wimage+width/zoom:
        result[0] = -wimage+width/zoom
    if x[1] < -himage+height/zoom:
        result[1] = -himage+height/zoom
    return result


def image_to_local(coords, offset, zoom):
    return tuple(o+c*zoom for c,o in zip(coords, offset))

def local_to_image(coords, offset, zoom):
    return tuple((c-o)/zoom for c,o in zip(coords, offset))




drag = False
drag_ref = [0,0]
while True:
    mpos = pygame.mouse.get_pos()
    keys = pygame.key.get_pressed()

    grid_move_step = 0.1

    old_zoom = zoom
    drag_off = [0,0]
    lmb_down = False
    lmb_up = False
    for event in pygame.event.get():

        if event.type == QUIT:
            pygame.quit()
            exit()
        elif event.type == MOUSEBUTTONDOWN:
            if event.button == RMB:
                drag = True
                drag_ref = mpos
            elif event.button == LMB:
                lmb_down = True
        elif event.type == MOUSEBUTTONUP:
            if event.button == RMB:
                drag = False
                offset[0] += mpos[0]-drag_ref[0]
                offset[1] += mpos[1]-drag_ref[1]
                offset = clamp_offset(offset)
            elif event.button == LMB:
                lmb_up = True
        elif event.type == MOUSEWHEEL:
            zoom += event.y
            if zoom < 1:
                zoom = 1
        elif event.type == KEYDOWN:
            if event.mod & KMOD_CTRL:
                if event.key == K_UP:
                    grid_size += 0.1
                elif event.key == K_DOWN:
                    grid_size -= 0.1
            else:
                if event.key == K_UP:
                    grid_offset[1] -= grid_move_step
                elif event.key == K_DOWN:
                    grid_offset[1] += grid_move_step
                elif event.key == K_LEFT:
                    grid_offset[0] -= grid_move_step
                elif event.key == K_RIGHT:
                    grid_offset[0] += grid_move_step

    if zoom != old_zoom:
        pg_grid_image = pygame.transform.scale_by(pg_grid_image_base, zoom)
        offset = [o+m*(1/zoom - 1/old_zoom) for o,m in zip(offset, mpos)]

        offset = clamp_offset(offset)

    if drag:
        drag_off = [a-b for a,b in zip(mpos, drag_ref)]

    drag_off = [x+y for x,y in zip(offset, drag_off)]

    if drag:
        drag_off = clamp_offset(drag_off)

    effective_offset = [x*zoom for x in drag_off]

    ex, ey = effective_offset

    mpos_image = local_to_image(mpos, effective_offset, zoom)

    if lmb_down:
        for entry in magic_points:
            if entry.start_drag(mpos_image, grid_size):
                break

    if lmb_up:
         for entry in magic_points:
            entry.stop_drag(mpos_image)

    for entry in magic_points:
        entry.update_drag(mpos_image)

    screen.blit(pg_grid_image, effective_offset)

    gx, gy = [x*zoom for x in grid_offset]
#    gx+N*grid_size*zoom = ex + width/zoom
#    N = (ex-gx)/(grid_size*zoom)

    gf = grid_size*zoom
    left = math.ceil((-ex-gx)/gf)
    right = math.floor((-ex-gx+width)/gf)
    top = math.ceil((-ey-gy)/gf)
    bot = math.floor((-ey-gy+height)/gf)

    radius = max(zoom, 3)

    for bbox in sprite_boxes:
        xl = ex+bbox[0]*zoom
        yt = ey+bbox[1]*zoom
        xr = ex+bbox[2]*zoom
        yb = ey+bbox[3]*zoom
        pygame.gfxdraw.rectangle(screen, pygame.Rect(xl, yt, xr-xl, yb-yt), (0,255,0))

#    for dx in range(left, right+1):
#        for dy in range(top, bot+1):
#            pygame.gfxdraw.filled_circle(screen, round(ex+gx+gf*dx), round(ey+gy+gf*dy), radius,(255,0,0))


    for entry in magic_points:
        entry.render(screen, mpos, (ex,ey), zoom, radius)

#    for x,y in extra_points:
#        pygame.gfxdraw.filled_circle(screen, round(ex+x*zoom), round(ey+y*zoom), radius,(0,255,255))


    pygame.display.update()
    time.sleep(0.05)



