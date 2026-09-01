import os

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "PressStart2P.ttf")
FONT_SIZE = 165  # circa 2.6cm di altezza lettere
LARGHEZZA_STAMPA = 576  # larghezza fisica massima della testina, non toccare
LIMITE_CARATTERI = 100


def crea_immagine_testo(testo, font_size=FONT_SIZE, larghezza_stampa=LARGHEZZA_STAMPA):
    font = ImageFont.truetype(FONT_PATH, font_size)
    img_temp = Image.new("1", (1, 1))
    draw_temp = ImageDraw.Draw(img_temp)
    bbox = draw_temp.textbbox((0, 0), testo, font=font)
    larghezza_testo = bbox[2] - bbox[0]
    altezza_testo = bbox[3] - bbox[1]

    margine_lunghezza = 20
    img = Image.new("1", (larghezza_testo + margine_lunghezza * 2, larghezza_stampa), 1)
    draw = ImageDraw.Draw(img)
    y_centrato = (larghezza_stampa - altezza_testo) // 2 - bbox[1]
    draw.text((margine_lunghezza - bbox[0], y_centrato), testo, font=font, fill=0)

    return img.rotate(90, expand=True)


def stampa_messaggio(stampante, testo):
    try:
        if len(testo) > LIMITE_CARATTERI:
            stampante.set(align="center", bold=True, width=1, height=1)
            stampante.text(f"MESSAGGIO TROPPO LUNGO\n(supera {LIMITE_CARATTERI} caratteri)\n")
            stampante.set(align="left", bold=False, width=1, height=1)
            return True

        stampante.set(align="center", bold=True, width=2, height=2)
        stampante.text("PROMPT:\n")
        stampante.set(align="left", bold=False, width=1, height=1)

        immagine = crea_immagine_testo(testo)
        stampante.image(immagine)
        return True
    except Exception:
        return False


def get_printer():
    from escpos.printer import Usb

    return Usb(0x0416, 0x5011, in_ep=0x81, out_ep=0x01)
