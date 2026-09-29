"""Borderless thought-cloud UI. No credentials or network requests live here."""
import ctypes
import math
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageChops

TRANSPARENT = '#ff00ff'
INK = '#51466C'
MUTED = '#8C819E'


def placement(px, py, pw, ph, sw, sh, body):
    width, height = 420, body+64
    if py >= height+10:
        mode, x, y = 'above', px+pw//2-width//2, py-height+4
    elif px+pw+484 <= sw:
        mode,x,y,width,height = 'right',px+pw-4,py-30,484,body
    elif px-484 >= 0:
        mode,x,y,width,height = 'left',px-484+4,py-30,484,body
    elif py+ph+height+8 <= sh:
        mode,x,y = 'below',px+pw//2-width//2,py+ph-4
    else:
        mode,x,y = 'above',px+pw//2-width//2,py-height+4
    return mode,max(4,min(x,sw-width-4)),max(4,min(y,sh-height-4)),width,height


def cloud_image(body, mode, anchor):
    w=420
    width,height=(484,body) if mode in ('left','right') else (w,body+64)
    ox,oy=(64,0) if mode=='right' else (0,64) if mode=='below' else (0,0)
    scale=3
    mask=Image.new('L',(width*scale,height*scale),0)
    draw=ImageDraw.Draw(mask)
    def ellipse(box):
        draw.ellipse(tuple(round(v*scale) for v in box),fill=255)
    def oval(box):
        x0,y0,x1,y1=box;ellipse((x0+ox,y0+oy,x1+ox,y1+oy))
    draw.rounded_rectangle(((ox+25)*scale,(oy+38)*scale,(ox+w-25)*scale,(oy+body-35)*scale),radius=45*scale,fill=255)
    for box in [(48,18,169,112),(123,5,282,113),(255,19,378,119),
                (7,65,113,166),(w-111,66,w-7,173),
                (9,body-160,121,body-48),(w-120,body-160,w-9,body-48),
                (47,body-113,184,body-8),(145,body-108,289,body-1),(260,body-114,382,body-12)]:
        oval(box)
    if mode in ('above','below'):
        a=max(66,min(354,anchor))
        bubbles=[(a-17,body+12,11),(a-6,body+34,7),(a,body+51,4)] if mode=='above' else [(a-17,51,11),(a-6,29,7),(a,12,4)]
    else:
        a=max(45,min(body-45,anchor))
        bubbles=[(51,a-13,11),(29,a-5,7),(12,a,4)] if mode=='right' else [(432,a-13,11),(454,a-5,7),(471,a,4)]
    for x,y,r in bubbles:ellipse((x-r,y-r,x+r,y+r))
    mask=mask.resize((width,height),Image.Resampling.LANCZOS).point(lambda p:255 if p>=128 else 0)
    edge=ImageChops.subtract(mask,mask.filter(ImageFilter.MinFilter(3)))
    image=Image.new('RGB',(width,height),TRANSPARENT)
    # Soft lavender silhouette under the white cloud, no rectangular window fill.
    shadow=Image.new('L',(width,height),0);shadow.paste(mask,(1,3))
    image.paste('#DBD4EA',(0,0,width,height),shadow)
    gradient=Image.new('RGB',(1,height))
    for y in range(height):
        t=y/max(height-1,1)
        gradient.putpixel((0,y),(round(255-8*t),round(254-11*t),255))
    image.paste(gradient.resize((width,height)),(0,0),mask)
    image.paste('#E4DCEE',(0,0,width,height),edge)
    return image,(ox,oy)


class ThoughtBubble:
    def __init__(self,pet):
        self.pet=pet
        self.window=tk.Toplevel(pet.root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg=TRANSPARENT)
        self.window.wm_attributes('-transparentcolor',TRANSPARENT)
        self.window.wm_attributes('-toolwindow',True)
        self.canvas=tk.Canvas(self.window,bg=TRANSPARENT,highlightthickness=0,bd=0)
        self.canvas.pack()
        self.visible=False
        self.page=0
        self.last_layout=None
        self.window.bind('<Escape>',lambda _:self.hide())
        self.canvas.bind('<MouseWheel>',self.wheel)
        pet.root.bind('<Escape>',lambda _:self.hide())

    def hide(self):
        self.visible=False
        self.window.withdraw()

    def show(self):
        self.visible=True
        self.page=0
        self.render()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        for key in (1,2):ctypes.windll.user32.GetAsyncKeyState(key)

    def turn(self,delta):
        report=self.pet.usage_report or {}
        pages=max(1,math.ceil(len(report.get('rows',[]))/2))
        self.page=(self.page+delta)%pages
        self.render()

    def wheel(self,event):
        if event.delta:self.turn(-1 if event.delta>0 else 1)

    def poll(self):
        if not self.visible:return
        for key in (1,2):
            if ctypes.windll.user32.GetAsyncKeyState(key)&0x8001:
                x,y=self.window.winfo_pointerxy()
                def inside(win):
                    return win.winfo_rootx()<=x<win.winfo_rootx()+win.winfo_width() and win.winfo_rooty()<=y<win.winfo_rooty()+win.winfo_height()
                if not inside(self.window) and not inside(self.pet.root):
                    self.hide();return

    def render(self):
        if not self.visible:return
        pet=self.pet
        report=pet.usage_report if pet.cfg.get('usage_enabled',True) else None
        enabled=pet.cfg.get('usage_enabled',True)
        rows=report.get('rows',[]) if report else []
        pages=max(1,math.ceil(len(rows)/2))
        self.page=min(self.page,pages-1)
        body=202 if not enabled else 295 if not rows else 326 if len(rows)==1 else 380
        mode,x,y,width,height=placement(pet.root.winfo_x(),pet.root.winfo_y(),pet.width,pet.height,pet.root.winfo_screenwidth(),pet.root.winfo_screenheight(),body)
        anchor=pet.root.winfo_x()+pet.width//2-x if mode in ('above','below') else pet.root.winfo_y()+30-y
        background,(ox,oy)=cloud_image(body,mode,anchor)
        self.background=ImageTk.PhotoImage(background)
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.window.wm_attributes('-topmost',bool(pet.cfg['topmost']))
        self.canvas.configure(width=width,height=height)
        self.canvas.delete('all')
        self.canvas.create_image(0,0,image=self.background,anchor='nw')
        def text(x,y,value,size=10,color=INK,bold=False,anchor='center',width=None,tag=None):
            return self.canvas.create_text(x+ox,y+oy,text=value,font=('Microsoft YaHei UI',size,'bold' if bold else 'normal'),fill=color,anchor=anchor,width=width or 0,tags=tag or ())
        def button(x,y,value,callback,tag):
            self.canvas.create_oval(x+ox-14,y+oy-13,x+ox+14,y+oy+13,fill='#EEE7F8',outline='',tags=tag)
            text(x,y,value,10,'#8B7B9F',tag=tag)
            self.canvas.tag_bind(tag,'<Button-1>',lambda _:callback())
            self.canvas.tag_bind(tag,'<Enter>',lambda _:self.canvas.configure(cursor='hand2'))
            self.canvas.tag_bind(tag,'<Leave>',lambda _:self.canvas.configure(cursor=''))
        text(210,44,'让我想一想…',9,MUTED)
        button(352,48,'×',self.hide,'close')
        text(210,76,pet.balance_state['label'],10,INK)
        amount=pet.balance_state['amount']
        text(210,109,amount,23 if len(amount)<21 else 17,pet.balance_state['color'],True,width=325)
        text(210,142,pet.balance_state['status'],8,MUTED,width=315)
        if not enabled:return
        self.canvas.create_line(65+ox,164+oy,355+ox,164+oy,fill='#E4DCED')
        if report:
            text(210,185,report['title'],9,INK,True,width=315)
            text(210,205,report['range'],8,MUTED,width=315)
            text(210,223,report['note'],8,MUTED,width=315)
        else:
            text(210,189,'最近用量',10,INK,True)
        if not rows:
            text(210,250,report['message'] if report else '等待查询后，在这里查看用量',9,MUTED,width=310)
        else:
            for i,row in enumerate(rows[self.page*2:self.page*2+2]):
                top=245+i*50
                model=row['model']
                if len(model)>35:model=model[:33]+'…'
                text(70,top,model,9,INK,True,anchor='w',width=285)
                tokens=f"{int(row['tokens']):,}" if row['tokens'] is not None else '未提供'
                cost=f"{row['actual_cost']:,.6f} USD" if row['actual_cost'] is not None else '未提供'
                text(70,top+20,f'Tokens {tokens}   ·   实际花费 {cost}',8,MUTED,anchor='w',width=285)
            if pages>1:
                button(159,347,'‹',lambda:self.turn(-1),'previous')
                text(210,347,f'{self.page+1} / {pages}',8,MUTED)
                button(261,347,'›',lambda:self.turn(1),'next')
