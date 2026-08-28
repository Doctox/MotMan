# Captures Play Store (1080 x 1920) : capture telephone recadree + bandeau.
# Les captures brutes viennent du telephone de JM (Android, 945x2048 apres
# passage par WhatsApp). On retire la barre d'etat et la barre de navigation
# d'Android : l'heure, l'operateur et le niveau de batterie n'apportent rien et
# datent la capture.
from PIL import Image, ImageDraw, ImageFont
import sys, os

CREAM=(253,245,224); GREEN=(5,81,57); ORANGE=(247,111,38)
W,H=1080,1920
_ICI = os.path.dirname(os.path.abspath(__file__))
PF = os.path.join(_ICI, 'fonts', 'playfair.ttf')
DM = os.path.join(_ICI, 'fonts', 'dmsans.ttf')

def font(path,size,weight):
    f=ImageFont.truetype(path,size)
    try: f.set_variation_by_axes([weight])
    except Exception: pass
    return f

# Barre d'etat et barre de navigation d'Android, mesurees sur les captures de JM
# (Samsung, 945 x 2048 apres passage par WhatsApp). Valeurs fixes plutot que
# detection automatique : la detection par luminosite se trompait sur la capture
# de victoire, dont le bas est occupe par un bouton vert sombre. Si le telephone
# ou la definition changent, remesurer ces deux nombres.
BARRE_ETAT = 85
DEBUT_BARRE_NAVIGATION = 1930

def rogner_barres(im):
    """Retire l'heure, l'operateur, la batterie et les touches systeme : ils
    n'apportent rien a la fiche et datent la capture."""
    w, h = im.size
    return im.crop((0, BARRE_ETAT, w, min(DEBUT_BARRE_NAVIGATION, h)))

def ajuster(d,texte,chemin,taille,poids,largeur_max):
    while taille>20:
        f=font(chemin,taille,poids)
        bb=d.textbbox((0,0),texte,font=f)
        if bb[2]-bb[0]<=largeur_max: return f
        taille-=2
    return font(chemin,taille,poids)

def composer(source,titre,soustitre,sortie):
    shot=rogner_barres(Image.open(source))
    toile=Image.new('RGB',(W,H),CREAM); d=ImageDraw.Draw(toile)
    ft=ajuster(d,titre,DM,62,700,W-120)
    fs=ajuster(d,soustitre,DM,34,400,W-140)
    def centrer(t,f,y):
        bb=d.textbbox((0,0),t,font=f)
        d.text((W/2-(bb[2]-bb[0])/2-bb[0],y),t,font=f,fill=GREEN)
    centrer(titre,ft,96)
    d.rectangle([W/2-46,192,W/2+46,197],fill=ORANGE)
    centrer(soustitre,fs,226)
    zone=H-300-60
    ratio=shot.width/shot.height
    h=zone; w=int(h*ratio)
    if w>W-140: w=W-140; h=int(w/ratio)
    shot=shot.resize((w,h),Image.LANCZOS)
    masque=Image.new('L',(w,h),0); ImageDraw.Draw(masque).rounded_rectangle([0,0,w-1,h-1],radius=34,fill=255)
    x=(W-w)//2; y=300+(zone-h)//2
    toile.paste(shot,(x,y),masque)
    d.rounded_rectangle([x,y,x+w-1,y+h-1],radius=34,outline=(214,203,178),width=3)
    toile.save(sortie,'PNG',optimize=True)
    print(os.path.basename(sortie), toile.size, f"{os.path.getsize(sortie)//1024} ko")

if __name__ == '__main__':
    src=sys.argv[1]; dst=sys.argv[2]
    plan=[
      ('WhatsApp Image 2026-08-28 at 18.46.00 (1).jpeg','1-duel.png',
       "Deux joueurs, une grille","Chacun son tour, sur la même grille."),
      ('WhatsApp Image 2026-08-28 at 18.46.00 (2).jpeg','2-defi.png',
       "Un défi chaque jour","La même grille pour tout le monde. Votre série grandit."),
      ('WhatsApp Image 2026-08-28 at 18.46.01 (2).jpeg','3-victoire.png',
       "Gagnez, montez, débloquez","Expérience et plumes à chaque partie."),
      ('WhatsApp Image 2026-08-28 at 18.46.01.jpeg','4-classement.png',
       "Où en êtes-vous ?","Classement général, ou seulement entre amis."),
      ('WhatsApp Image 2026-08-28 at 18.46.01 (1).jpeg','5-epicerie.png',
       "Tout est cosmétique","Avatars, cadres, animations. Aucun avantage à acheter."),
    ]
    for fichier,nom,titre,soustitre in plan:
        composer(os.path.join(src,fichier), titre, soustitre, os.path.join(dst,nom))
