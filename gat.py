from collections import defaultdict

import tabulate

from gimpformats.gimpXcfDocument import GimpDocument

from PIL import Image, ImageChops

from morphsuit import morph, gimp

#0, 6, 13, 20, 27, 34
N=5 #color hold length in frames
masks = {
'red': (20,0),
'blue': (0,2),
'1r1b': (6,1),
'2r1b': (13,3),
'1r2b': (34,0),
'2r2b': (27,4),
'extra': (13,3),
}

project = gimp.GimpProject('inputs.xcf', 'output')

print(project.variables)
#project.export_layers('tools')

old_coords = []
coords = project.variables['r']
print(coords)

import numpy as np

pixel_size,tile_size = project._get_export_sizes(None, None)
scale_factor = tile_size/pixel_size
print(scale_factor)

pixel_size = ((2078-128)**2+(1622-84)**2)**0.5
tile_size = (37**2+29**2)**0.5

scale_factor = tile_size/pixel_size
print(scale_factor)

#pixel_size = ((1127.5-1023.5)**2+(1035.5-928.5)**2)**0.5
#tile_size = (2**2+1**2)**0.5

#scale_factor = tile_size/pixel_size
#print(scale_factor)



#37, 29
#123,84
#2078,1622

for idx, vals in enumerate(coords):

    _vals = tuple(x*scale_factor*8 for x in vals)
    old_coords.append(_vals)

    vals = tuple(x*scale_factor for x in vals)
    vals = tuple(x-int(x) for x in vals)

    vals = tuple(x*8 for x in vals)

    coords[idx] = vals

cols = list(zip(*coords))

avgs = [sum(x)/len(x) for x in cols]
devs = [np.std(x) for x in cols]

print(avgs)
print(devs)

#for key,val in coords.items():

grid_offset = avgs
extra_points = old_coords

import time
import math
import pygame
import pygame.gfxdraw
import pygame.transform
from pygame.locals import *


pygame.init()

grid_image = project.layers['grid'].image
pg_grid_image_base = pygame.image.fromstring(grid_image.tobytes(), grid_image.size, grid_image.mode)

wimage, himage = pg_grid_image_base.get_size()

width, height = 1500,1000
screen=pygame.display.set_mode((width, height))

zoom = 4
offset = [0,0]

grid_size = pixel_size/tile_size
ingame_pixel_size = grid_size/8

grid_offset = [x*ingame_pixel_size for x in grid_offset]
extra_points = [tuple(y*ingame_pixel_size for y in x) for x in extra_points]
print(extra_points)

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


drag = False
drag_ref = [0,0]
while True:
    mpos = pygame.mouse.get_pos()
    keys = pygame.key.get_pressed()

    grid_move_step = 0.1

    old_zoom = zoom
    drag_off = [0,0]
    for event in pygame.event.get():

        if event.type == QUIT:
            pygame.quit()
            exit()
        elif event.type == MOUSEBUTTONDOWN:
            drag = True
            drag_ref = mpos
        elif event.type == MOUSEBUTTONUP:
            drag = False
            offset[0] += mpos[0]-drag_ref[0]
            offset[1] += mpos[1]-drag_ref[1]
            offset = clamp_offset(offset)

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
        offset = clamp_offset(offset)

    if drag:
        drag_off = [a-b for a,b in zip(mpos, drag_ref)]

    drag_off = [x+y for x,y in zip(offset, drag_off)]

    if drag:
        drag_off = clamp_offset(drag_off)


    effective_offset = [x*zoom for x in drag_off]
    ex, ey = effective_offset

    screen.blit(pg_grid_image, effective_offset)

    gx, gy = [x*zoom for x in grid_offset]
#    gx+N*grid_size*zoom = ex + width/zoom
#    N = (ex-gx)/(grid_size*zoom)

    gf = grid_size*zoom
    left = math.ceil((-ex-gx)/gf)
    right = math.floor((-ex-gx+width)/gf)
    top = math.ceil((-ey-gy)/gf)
    bot = math.floor((-ey-gy+height)/gf)
#    print(left, right, top, bot)

#    print(ex-gx)
#    print(ex-gx+width/zoom)
#    print(gf)


    radius = max(zoom, 3)

    for dx in range(left, right+1):
        for dy in range(top, bot+1):
            pygame.gfxdraw.filled_circle(screen, round(ex+gx+gf*dx), round(ey+gy+gf*dy), radius,(255,0,0))

    for x,y in extra_points:
        pygame.gfxdraw.filled_circle(screen, round(ex+x*zoom), round(ey+y*zoom), radius,(0,255,255))


    pygame.display.update()
    time.sleep(0.05)



