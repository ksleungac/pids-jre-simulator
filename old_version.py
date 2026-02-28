import os
from os import environ
from draw_util import *
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame
from win32 import win32gui
import keyboard
import soundfile as sf
import pyloudnorm as pyln
import json
import time
import pygame.gfxdraw
import math

work_dir = input("車内放送&発車メロディー files location:")
# work_dir = "E:\shit\Keiyo"
# work_dir = "E:/shit/Nanbu/4027F"

# Load files
json_dir = os.path.join(work_dir, "route.json")
route = json.load(open(json_dir, encoding="utf8"))
stops = route["stops"]
route_name = route["route"]
train_type = route["type"]

color = [255, 255, 255]
if route["color"] is not None:
    color = route["color"]

contrast_color = [224,54,37]
if "contrast_color" in route.keys():
    contrast_color = route["contrast_color"]

type_color = [0,0,0]
if "type_color" in route.keys():
    type_color = route["type_color"]

dest = "undefined"
if route["dest"] is not None:
    dest = route["dest"]

# Set up pygame
pygame.init()
pygame.mixer.init()
pygame.display.set_caption('春日影？！')
clock = pygame.time.Clock()
FONT_N = pygame.font.SysFont('shingopr6nmedium', 25)
S_WIDTH = 730
S_HEIGHT = 420
screen = pygame.display.set_mode((S_WIDTH, S_HEIGHT))
win32gui.SetWindowPos(pygame.display.get_wm_info()['window'], -1, S_WIDTH, S_HEIGHT, 0, 0, 1)

class LCD_state:
    def __init__(self) -> None:
        self.curr_stop = 0
        self.cnt_pa = 0
        self.cnt_sta = 0
        self.circular = 1 if stops[0]['name'] == stops[-1]['name'] else 0
    
    def event_play_pa(self):
        dest_idx = 0
        try:
            dest_idx=[s["name"] for s in stops].index(dest)
        except:
            dest_idx=self.STOPS_QUANTITY-1

        if self.curr_stop==dest_idx:
            return
        
        self.cnt_pa += 1
        if self.cnt_pa >= len(stops[self.curr_stop]['pa']):
            if self.curr_stop < len(stops)-1:
                self.curr_stop += 1
                self.cnt_pa = 0
                pis.increment_curr_stop_disp()
                if len(stops[self.curr_stop]["pa"])==0:
                    while(len(stops[self.curr_stop]["pa"])==0):
                        self.curr_stop+=1
            elif self.circular == 1:
                self.curr_stop = 0; self.cnt_pa = 0; pis.curr_stop_disp = 0
            else:
                self.cnt_pa -= 1
            self.cnt_sta = 0
            next_pa()
            pis.show_stops()
            return
        pis.increment_curr_stop_disp()
        next_pa()
        pis.show_stops()

    def event_play_sta(self):
        if self.cnt_sta < len(stops[self.curr_stop]['sta'])-1:
            self.cnt_sta += 1

class LOWER:
    def __init__(self) -> None:
        l = len(stops)
        per_line = min(14, math.ceil(l / 2)) if l > 17 or l % 2 == 0 else 17
        self.stops_w = 42

        self.x = (S_WIDTH - self.stops_w*per_line) // 2
        self.y = int(S_HEIGHT * .28)
        self.curr_stop_disp = state_control.curr_stop
        self.BAR_HEIGHT = 30
        self.STOPS_QUANTITY = per_line*2
        self.per_line = per_line
        
        self.h_line = 105 if l>per_line else 150
        self.top_pad = 40
        self.circular = 1 if stops[0]['name'] == stops[-1]['name'] else 0
        self.continuity = [0, 0, 0]
        if self.circular == 1 or len(stops)>28:
            self.continuity = [1, 1, 1]
        elif len(stops) > per_line:
            self.continuity = [1, 1, 0]
        
        self.timer = 0
        self.FONT_STOPS = pygame.font.SysFont('shingopr6nmedium', 17)
        self.FONT_TIME = pygame.font.SysFont('helveticaneue', 14)
        self.skip=0

    def increment_curr_stop_disp(self):
        f_stops = self.get_stops_list_disp()
        dest_idx = 0
        try:
            dest_idx=[s["name"] for s in f_stops].index(dest)
        except:
            dest_idx=self.STOPS_QUANTITY-1

        if self.curr_stop_disp==dest_idx:
            return

        if (len(f_stops[self.curr_stop_disp+1]["pa"])==0):
            self.curr_stop_disp+=1
            if state_control.cnt_pa==0:
                i = self.curr_stop_disp
                while(len(f_stops[i]["pa"])==0):
                    i+=1
                self.skip=i-self.curr_stop_disp
                if (len(f_stops[self.curr_stop_disp+self.skip]["pa"])==1):
                    self.curr_stop_disp += self.skip
                    self.skip=0 

            elif state_control.cnt_pa>=1 or stops[state_control.cnt_pa]==1:
                self.curr_stop_disp += self.skip-1
                self.skip=0
        elif state_control.cnt_pa==0:
            self.curr_stop_disp+=1
        else:
            self.skip=0
                

    def refresh_curr_stop_disp(self):
        if (len(stops) - state_control.curr_stop == self.STOPS_QUANTITY-1):
            if self.circular != 1:
                self.continuity = [1, 1, 0]
            self.curr_stop_disp = 1


    def get_stops_list_disp(self):
        if len(stops) <= self.STOPS_QUANTITY:
            return stops
        
        f_stops = stops[:self.STOPS_QUANTITY]
        if (len(stops) - state_control.curr_stop < self.STOPS_QUANTITY):
            f_stops = stops[len(stops) - self.STOPS_QUANTITY:]
            self.refresh_curr_stop_disp()
        return f_stops
    
    def get_line(self, i):
        return 1 if i < self.per_line else 2
    
    def draw_ptr(self):
        x = self.x; y = self.y
        ptr_color = contrast_color
        ptr = (self.curr_stop_disp % self.per_line) * self.stops_w
        l_y = y + self.h_line*self.get_line(self.curr_stop_disp) + self.top_pad*(self.get_line(self.curr_stop_disp)-1)

        if state_control.curr_stop != 0:
            w = 18
            offset = int(w*0.8)
            draw_aapolygon(screen, (230, 230, 230), arrow_points(x + ptr-offset-2, l_y, 23, self.BAR_HEIGHT, 16), 5)
            draw_aapolygon(screen, ptr_color, arrow_points(x + ptr-offset, l_y - 2, w, self.BAR_HEIGHT+4, 10))
        else:
            overhang = 2 
            points = [(x,l_y-overhang), (x, l_y+self.BAR_HEIGHT+overhang), (x+self.stops_w-10, l_y+self.BAR_HEIGHT+overhang),
                        (x+self.stops_w-2, l_y+self.BAR_HEIGHT/2), (x+self.stops_w-10, l_y-overhang)]
            draw_aapolygon(screen, (230,230,230), [(i+3, j) for (i,j) in points])
            draw_aapolygon(screen, ptr_color, points)

    def draw_marks(self):
        f_stops = self.get_stops_list_disp()
        x = self.x; y = self.y
        ptr = 0

        dest_idx = 0
        try:
            dest_idx=[s["name"] for s in f_stops].index(dest)
        except:
            dest_idx=self.STOPS_QUANTITY-1
        
        for i, stop in enumerate(f_stops):
            ptr = (i % self.per_line) * self.stops_w
            l_y = y + self.h_line*self.get_line(i) + self.top_pad*(self.get_line(i)-1)
            offset = self.stops_w // 2
            center_x = x + ptr + offset
            center_y = l_y + self.BAR_HEIGHT//2
            if i >= self.curr_stop_disp and i <= dest_idx:
                if i==0 and self.curr_stop_disp==0:
                    radius = 5
                    pygame.gfxdraw.filled_circle(screen, center_x, center_y, radius, (230, 230, 230))
                    pygame.gfxdraw.aacircle(screen, center_x, center_y, radius, (230, 230, 230))
                elif len(stop["pa"]) == 0:
                    w = 20
                    offset = int(self.stops_w*0.3)
                    draw_aapolygon(screen, (230, 230, 230), arrow_points(x + ptr + offset, l_y + 4, 14, self.BAR_HEIGHT-8, 6))                    
                else:
                    radius = 11
                    pygame.gfxdraw.filled_circle(screen, center_x, center_y, radius, (230, 230, 230))
                    pygame.gfxdraw.aacircle(screen, center_x, center_y, radius, (230, 230, 230))
                    if i == self.curr_stop_disp or (i-self.skip==self.curr_stop_disp):
                        pygame.gfxdraw.filled_circle(screen, center_x, center_y, radius-2, (175, 150, 6))
                        pygame.gfxdraw.aacircle(screen, center_x, center_y, radius-2, (175, 150, 6))

            else:
                radius = 5
                pygame.gfxdraw.filled_circle(screen, center_x, center_y, radius, (230, 230, 230))
                pygame.gfxdraw.aacircle(screen, center_x, center_y, radius, (230, 230, 230))

    def draw_times(self):
        f_stops = self.get_stops_list_disp()
        x = self.x; y = self.y
        ptr = 0
        time = 0
        
        dest_idx = 0
        try:
            dest_idx=[s["name"] for s in f_stops].index(dest)
        except:
            dest_idx=self.STOPS_QUANTITY-1

        for i, stop in enumerate(f_stops):
            if i==0 and self.curr_stop_disp==0:
                continue

            ptr = (i % self.per_line) * self.stops_w
            l_y = y + self.h_line*self.get_line(i) + self.top_pad*(self.get_line(i)-1)
            if i >= self.curr_stop_disp:
                t_w, t_h = self.FONT_TIME.size("0")

                if "time" in stop.keys():
                    time += stop["time"]
                    time_x = x + ptr + (self.stops_w-t_w*len(str(time)))//2
                    time_y = l_y + (self.BAR_HEIGHT-t_h)//2
                    draw_text(f'{time}', self.FONT_TIME, (25, 25, 25), time_x, time_y)

                if i == self.per_line-1 or i==dest_idx:
                    f = pygame.font.SysFont('shingopr6nmedium', 11)
                    t_w, t_h = f.size("分")
                    y_offset = (self.BAR_HEIGHT -t_h)//2


                    pygame.draw.rect(screen, color, pygame.Rect(x + ptr + self.stops_w, l_y, t_w, self.BAR_HEIGHT))
                    pygame.draw.rect(screen, (230, 230, 230), pygame.Rect(x + ptr + self.stops_w + t_w-3, l_y, 3, self.BAR_HEIGHT))
                    draw_text("分", f, (230, 230, 230), x + ptr+self.stops_w*0.85, l_y + y_offset) 
        

    def show_stops(self):
        f_stops = self.get_stops_list_disp()
        x = self.x; y = self.y
        ptr = 0
        pygame.draw.rect(screen, (230, 230, 230), pygame.Rect(0, y, S_WIDTH, 400))
        if frame_mode == 0:
            return
        
        dest_idx = 0
        try:
            dest_idx=[s["name"] for s in f_stops].index(dest)
        except:
            dest_idx=self.STOPS_QUANTITY-1
        
        for i, stop in enumerate(f_stops):

            ptr = (i % self.per_line) * self.stops_w
            l_y = y + self.h_line*self.get_line(i) + self.top_pad*(self.get_line(i)-1)
            if i >= self.curr_stop_disp and i <= dest_idx:
                pygame.draw.rect(screen, color, pygame.Rect(x + ptr, l_y, self.stops_w, self.BAR_HEIGHT))                
                draw_stops_text(self.FONT_STOPS, stop["name"], (110, 110, 110) if len(stop["pa"])==0 and i!=0 else (0, 0, 0), x + ptr, l_y-7)
            else:
                pygame.draw.rect(screen, (110, 110, 110), pygame.Rect(x + ptr, l_y, self.stops_w, self.BAR_HEIGHT))
                draw_stops_text(self.FONT_STOPS, stop["name"], (110, 110, 110), x + ptr, l_y-7)

        self.draw_ptr()
        self.draw_marks()
        self.draw_times()
        


        # if self.continuity[0]:
        #     draw_continuity_r(screen, color if self.curr_stop_disp < 14 else (130, 130, 130), x + 14*50 - 10, y + line_height, self.BAR_HEIGHT)
        # if self.continuity[1]:
        #     draw_continuity_l(screen, color if self.curr_stop_disp < 15 else (130, 130, 130), x-25, y + line_height*2 + 40, self.BAR_HEIGHT)
        # if self.continuity[2]:
        #     loc = (len(stops) - 14) if len(stops) <= 28 else 14
        #     draw_continuity_r(screen, color if self.curr_stop_disp < 28 else (130, 130, 130), x + loc*50 - 10, y + line_height*2 + 40, self.BAR_HEIGHT)


        pygame.display.flip()
        
class UPPER:
    def __init__(self) -> None:
        self.x = 0
        self.y = 0
        self.h = int(S_HEIGHT * .28)
        self.dark_bg = [25, 25, 25]
        self.white_bg = [230, 230, 230]
        self.clock = ""

    def draw_init(self):
        pygame.draw.rect(screen, self.dark_bg, pygame.Rect(0, 0, S_WIDTH, self.h))

        #train type
        box_w =  150
        FONT_N_I = pygame.font.SysFont('shingopr6nheavy', 26, bold=True, italic=True)
        pygame.draw.rect(screen, self.white_bg, pygame.Rect(15, 5, box_w, 31), 0, 2)
        if len(train_type) > 2:
            draw_text_given_width(15, 7, box_w, FONT_N_I, train_type, type_color, collapse=True)
        else:
            draw_text_given_width(15, 7, box_w, FONT_N_I, train_type, type_color, exp=False)

        #destination
        FONT_ML_I = pygame.font.SysFont('shingopr6nmedium', 35)
        draw_text_given_width(15, 50, box_w, FONT_ML_I, dest, self.white_bg)
        FONT_S = pygame.font.SysFont('shingopr6nmedium', 18)

        if route_name == "山手線":
            t_w, t_h = FONT_S.size("方面")
            draw_text("方面", FONT_S, (self.white_bg), int(S_WIDTH * 0.25)-t_w-10, self.h-t_h-5)
        else:
            t_w, t_h = FONT_S.size("ゆき")
            draw_text("ゆき", FONT_S, (self.white_bg), int(S_WIDTH * 0.25)-t_w-10, self.h-t_h-5)
    
        #color band
        pygame.draw.rect(screen, color, pygame.Rect(int(S_WIDTH * 0.25), 0, 30, self.h-7))

        #prefix
        l = int(S_WIDTH * 0.25) + 40
        FONT_SS = pygame.font.SysFont('shingopr6nmedium', 25)
        pygame.draw.rect(screen, self.dark_bg, pygame.Rect(l, 5, 130, 30))
        draw_text(f"ただいま", FONT_SS, self.white_bg, l, 5)

        #stop name
        FONT_LL = pygame.font.SysFont('shingopr6nmedium', 78)
        name = stops[state_control.curr_stop]["name"].replace(" ", "")
        t_w, t_h = FONT_LL.size(name)
        pygame.draw.rect(screen, self.dark_bg, pygame.Rect(S_WIDTH*0.40, self.h-t_h-5, S_WIDTH*0.54, t_h+5))
        draw_text_given_width(S_WIDTH*0.40, self.h-t_h-5, S_WIDTH*0.54, FONT_LL, name, self.white_bg)

        pygame.display.flip()
    
    def draw_stop(self):
        #prefix
        l = int(S_WIDTH * 0.25) + 40
        FONT_SS = pygame.font.SysFont('shingopr6nmedium', 25)
        pygame.draw.rect(screen, self.dark_bg, pygame.Rect(l, 5, 130, 30))
        if state_control.cnt_pa == 0:
            draw_text(f"次は", FONT_SS, self.white_bg, l, 5)
        elif state_control.cnt_pa == 1:
            draw_text(f"まもなく", FONT_SS, self.white_bg, l, 5)

        #stop name
        FONT_LL = pygame.font.SysFont('shingopr6nmedium', 78)
        name = stops[state_control.curr_stop]["name"].replace(" ", "")
        t_w, t_h = FONT_LL.size(name)
        pygame.draw.rect(screen, self.dark_bg, pygame.Rect(S_WIDTH*0.40, self.h-t_h-5, S_WIDTH*0.54, t_h+5))
        draw_text_given_width(S_WIDTH*0.40, self.h-t_h-5, S_WIDTH*0.54, FONT_LL, name, self.white_bg)

        #hint square
        if len(stops[state_control.curr_stop]["pa"]) > 1:
            pygame.draw.rect(screen, (247,225,158), pygame.Rect((S_WIDTH-20, 80, 20, 20)))
        else:
            pygame.draw.rect(screen, self.dark_bg, pygame.Rect((S_WIDTH-20, 80, 20, 20)))
        pygame.display.flip()
    
    def draw_clock(self, t):
        l = S_WIDTH-160
        curr_time = time.strftime('%H:%M', time.localtime(t))
        self.clock = curr_time
        pygame.draw.rect(screen, self.dark_bg, pygame.Rect(l, 5, 80, 25))
        FONT_T = pygame.font.SysFont('helveticaneueroman', 26)
        draw_text(f"{curr_time}", FONT_T, self.white_bg, l, 0)
        pygame.display.flip()


# Initialize Station Control 
state_control = LCD_state()
pis = LOWER()
up = UPPER()
frame_mode = 1

def draw_text_given_width(x, y, w, font, text, color, exp=True, collapse=False):
    t_w, t_h = font.size(text)
    t_w_s = t_w // len(text)
    if t_w > w:
        ll = len(text)
        sep = w / ll
        hr = w / (ll*t_w_s)
        for i, t in enumerate(text):
            x_cord = x + sep*i
            draw_text(f"{t}", font, (color), x_cord, y, hr=hr)
    else:
        sep = (w-t_w) // (len(text)+1)
        if len(text)==2 and exp != False:
            exp = 7

        if collapse:
            draw_text(f"{text}", font, (color), x + (w-t_w) // 2, y)
        else:
            for i, t in enumerate(text):
                x_cord = x + sep*(i+1) + i*(t_w_s) + (exp if i>0 else -(exp))
                draw_text(f"{t}", font, (color), x_cord, y)

def draw_stops_text(font, stop_text, text_color, x, y):
    t = stop_text.split()
    _, t_h = font.size(stop_text)
    w = pis.stops_w
    if len(t) > 1:
        r_col_offset = 10
        offset = (w-t_h*2) / 2
        draw_1col_text(font, t[0], x+offset+t_h, y-6, 74, text_color)
        draw_1col_text(font, t[1], x+offset, y, 80-r_col_offset, text_color)
    else:
        offset = (w-t_h) / 2
        if len(t[0]) == 1:
            draw_1col_text(font, t[0], x+offset, y, 48, text_color)
        else:
            draw_1col_text(font, t[0], x+offset, y, 80, text_color)
        

def draw_1col_text(font, t, x, y, vert_space, text_color):
    _, t_h = font.size(t)
    length = len(t)
    vert_dist = (vert_space-t_h) / (length-1) if length>1 else 20
    vr = 1
    if length * t_h > vert_space:
        vr = vert_space / (length * t_h)  
        vert_dist = vert_dist + (t_h - (t_h * vr)) / (length-1)
    for k, s in enumerate(t):
        draw_text(f'{s}', font, text_color, x, y - vert_space + vert_dist * k, vr=vr)



def next_pa():
    up.draw_stop()
    if len(stops[state_control.curr_stop]["pa"]) <= 0:
        return
    
    trk = os.path.join(work_dir, "pa/", stops[state_control.curr_stop]["pa"][state_control.cnt_pa] + ".mp3")
    if not os.path.isfile(trk):
        return
    
    pygame.mixer.music.unload()
    if os.path.exists("new_file.mp3"):
        os.remove("new_file.mp3")
    trk = os.path.join(work_dir, "pa/", stops[state_control.curr_stop]["pa"][state_control.cnt_pa] + ".mp3")

    loud_norm(trk)
    pygame.mixer.music.load('./new_file.mp3')
    pygame.mixer.music.play(fade_ms=800)

def next_sta():
    
    if len(stops[state_control.curr_stop]["sta"]) <= 0:
        return

    trk = os.path.join(work_dir, "sta/", stops[state_control.curr_stop]["sta"][state_control.cnt_sta] + ".mp3")
    if not os.path.isfile(trk):
        return

    if pygame.mixer.music.get_busy():
        pygame.mixer.music.rewind()
        pygame.mixer.music.set_pos(stops[state_control.curr_stop]["sta_cut"])

    pygame.mixer.music.unload()
    if os.path.exists("new_file.mp3"):
        os.remove("new_file.mp3")

    loud_norm(trk)
    pygame.mixer.music.load('./new_file.mp3')
    pygame.mixer.music.play(fade_ms=800)     
        

def draw_text(text, font, text_col, x, y, bg=(0, 0, 0), hr=1, vr=1):
    if bg == (0, 0, 0):
        img = font.render(text, True, text_col).convert_alpha()
        txt_w, txt_h = img.get_size()
        img = pygame.transform.smoothscale(img, (txt_w * hr, txt_h * vr))
    else:
        img = font.render(text, True, text_col, bg)
    screen.blit(img, (x, y))

def reset_size():
    pygame.display.set_mode((S_WIDTH, S_HEIGHT))
    screen.fill((255, 255, 255))
    win32gui.SetWindowPos(pygame.display.get_wm_info()['window'], -1, S_WIDTH, S_HEIGHT, 0, 0, 1)

    up.draw_stop()
    pis.show_stops()
    pygame.display.flip()

def small_size():
    pygame.display.set_mode((400, 200))
    win32gui.SetWindowPos(pygame.display.get_wm_info()['window'], -1, 400, 100, 0, 0, 1)
    screen.fill((255, 255, 255))
    pygame.draw.rect(screen, (240, 240, 240), pygame.Rect(0, 0, S_WIDTH, 120))
    pygame.draw.rect(screen, color, pygame.Rect(20, 10, 10, 55))
    draw_text(f"{route_name}", FONT_N, (0, 0, 0), 40, 10, (240, 240, 240))
    draw_text(f"{train_type}", FONT_N, (0, 0, 0), 40, 45, (240, 240, 240))
    text_width, text_height = FONT_N.size(dest)
    draw_text(f"{dest}", FONT_N, (0, 0, 0), 400 - text_width - 55, 27, (240, 240, 240))
    if route_name == "山手線":
        draw_text(f"方面", FONT_N, (0, 0, 0), 400-55, 27, (240, 240, 240))
    else:
        draw_text(f"行", FONT_N, (0, 0, 0), 400-55, 27, (240, 240, 240))

reset_size()
up.draw_init()

running = True
while running:
    clock.tick(15)
    TIME = time.time()
    up.draw_clock(TIME)

    if keyboard.is_pressed('page down'):
        state_control.event_play_pa()
        pygame.time.wait(200)
    elif keyboard.is_pressed('page_up'):
        next_sta()
        state_control.event_play_sta()
    elif keyboard.is_pressed('end') and pygame.mixer.music.get_busy():
        pygame.mixer.music.pause()
    elif keyboard.is_pressed('home'):
        # if frame_mode == 1:
        #     frame_mode = 0
        #     small_size()
            
            
        # elif frame_mode == 0:
        #     frame_mode = 1
        #     reset_size()
            
        pygame.time.wait(200)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

pygame.quit()