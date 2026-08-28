# Image de presentation Play Store (1024 x 500) pour MotMan.
# Couleurs echantillonnees dans motman-icon-master.png, polices = celles de l'app.
# Relancer apres modification : python3 build-feature-graphic.py
from PIL import Image, ImageDraw, ImageFont
import os

CREAM=(253,245,224); GREEN=(5,81,57); ORANGE=(247,111,38)
W,H=1024,500
img=Image.new('RGB',(W,H),CREAM); d=ImageDraw.Draw(img)

def f(path,size,wght):
    ft=ImageFont.truetype(path,size)
    try: ft.set_variation_by_axes([wght])
    except Exception: pass
    return ft

_ICI = os.path.dirname(os.path.abspath(__file__))
PF = os.path.join(_ICI, 'fonts', 'playfair.ttf')
DM = os.path.join(_ICI, 'fonts', 'dmsans.ttf')
title=f(PF,96,700); tag=f(DM,38,600); sub=f(DM,23,400); cell=f(DM,46,600)

x=72
d.text((x,120),"MotMan",font=title,fill=GREEN)
d.text((x,236),"Duel de mots fléchés",font=tag,fill=GREEN)
d.rectangle([x,300,x+64,305],fill=ORANGE)
d.text((x,330),"Un défi chaque jour.",font=sub,fill=GREEN)
d.text((x,362),"Sans publicité, sans pay-to-win.",font=sub,fill=GREEN)

# --- grille 4 x 3, sans case de definition (choix de JM)
C=100; COLS,ROWS=4,3
gx,gy=556,100
gw,gh=COLS*C,ROWS*C
RAD=30
for i in range(1,COLS): d.line([gx+i*C,gy,gx+i*C,gy+gh],fill=GREEN,width=4)
for j in range(1,ROWS): d.line([gx,gy+j*C,gx+gw,gy+j*C],fill=GREEN,width=4)

def box(c,r): return (gx+c*C,gy+r*C,gx+(c+1)*C,gy+(r+1)*C)
# n'arrondir QUE le coin qui touche le bord exterieur de la grille
def corners_of(c,r):
    return (c==0 and r==0, c==COLS-1 and r==0, c==COLS-1 and r==ROWS-1, c==0 and r==ROWS-1)

def letter(c,r,ch,color,bg=None):
    x0,y0,x1,y1=box(c,r)
    if bg:
        co=corners_of(c,r)
        d.rounded_rectangle([x0+2,y0+2,x1-2,y1-2],radius=RAD if any(co) else 0,fill=bg,corners=co)
    bb=d.textbbox((0,0),ch,font=cell)
    d.text(((x0+x1)/2-(bb[2]-bb[0])/2-bb[0],(y0+y1)/2-(bb[3]-bb[1])/2-bb[1]),ch,font=cell,fill=color)

for i,ch in enumerate("DUEL"): letter(i,0,ch,GREEN)      # mot du joueur vert
letter(0,1,"U",GREEN)                                     # DUO en vertical
letter(0,2,"O",GREEN)                                     # case de croisement
for i,ch in enumerate("SER"): letter(i+1,2,ch,CREAM,bg=ORANGE)   # mot du joueur orange

d.rounded_rectangle([gx,gy,gx+gw,gy+gh],radius=RAD,outline=GREEN,width=6)

img.save('motman-feature-1024x500.png','PNG',optimize=True)
