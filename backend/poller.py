import requests
import time
from PIL import Image, ImageDraw, ImageFont
from escpos.printer import Usb

API_URL = "https://txtinstallazione.info-cuoredinapoli.workers.dev"
INTERVALLO_SECONDI = 2
LIMITE_CARATTERI = 100

FONT_PATH = "/home/pi/txtinstallazione/fonts/PressStart2P.ttf"
FONT_SIZE = 165  # circa 2.6cm di altezza lettere
LARGHEZZA_STAMPA = 576  # larghezza fisica massima della testina, non toccare

printer = Usb(0x0416, 0x5011, in_ep=0x81, out_ep=0x01)

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

def stampa_messaggio(testo):
    try:
        if len(testo) > LIMITE_CARATTERI:
            print(f"Messaggio troppo lungo ({len(testo)} caratteri), non lo stampo per intero.")
            printer.set(align="center", bold=True, width=1, height=1)
            printer.text(f"MESSAGGIO TROPPO LUNGO\n(supera {LIMITE_CARATTERI} caratteri)\n")
            printer.set(align="left", bold=False, width=1, height=1)
            return True

        printer.set(align="center", bold=True, width=2, height=2)
        printer.text("PROMPT:\n")
        printer.set(align="left", bold=False, width=1, height=1)

        immagine = crea_immagine_testo(testo)
        printer.image(immagine)
        return True
    except Exception as errore:
        print(f"Errore durante la stampa: {errore}")
        return False

def controlla_messaggi():
    try:
        risposta = requests.get(f"{API_URL}/message/latest", timeout=10)
        dati = risposta.json()

        if dati.get("pending"):
            messaggio_id = dati["id"]
            testo = dati["text"]

            print("=" * 40)
            print("NUOVO MESSAGGIO:")
            print(testo)
            print("=" * 40)

            stampato = stampa_messaggio(testo)

            if stampato:
                conferma = requests.post(
                    f"{API_URL}/message/ack",
                    json={"id": messaggio_id},
                    timeout=10
                )
                if conferma.ok:
                    print(f"Messaggio {messaggio_id} gestito e confermato.\n")
                else:
                    print(f"Gestito ma errore nella conferma del messaggio {messaggio_id}\n")
            else:
                print(f"Messaggio {messaggio_id} NON gestito, riprover al prossimo giro.\n")
        else:
            print("Nessun messaggio in attesa...")

    except requests.exceptions.RequestException as errore:
        print(f"Errore di connessione: {errore}")

if __name__ == "__main__":
    print("Avvio polling del middleware...")
    print(f"Controllo ogni {INTERVALLO_SECONDI} secondi. Premi Ctrl+C per fermare.\n")

    while True:
        controlla_messaggi()
        time.sleep(INTERVALLO_SECONDI)
