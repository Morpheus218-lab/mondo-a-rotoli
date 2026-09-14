#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TextWall - test scritta scorrevole sul ledwall.

Scrivi una parola nel terminale, premi Invio: la parola scorre sul muro.

Lo STADIO DI USCITA (geometria + protocollo) e' ripreso identico da Ombra.py:

  ESP (principale, UDP)
    8 ESP, uno per pannello 15x44 -> tela totale 120x44
    (i pannelli non in rete si segnano None: la tela resta 120 di larghezza)
    porta 4210, dati RGB row-major
    gamma 2.5 applicata QUI (il firmware NON corregge)
    serpentina orizzontale applicata QUI (il firmware scrive dritto nel buffer)
    ogni pannello = 2 pacchetti UDP da 991 byte: [indice 0|1] + 22 righe
    pausa 3 ms tra un pannello e l'altro

  ARDUINO (secondario, seriale) - disattivato di default
    56x32 = 7 pannelli 8x32, magic header FF 4C 45, handshake 'K'

Comandi da terminale:
  <testo>       manda la scritta (sostituisce quella in corso)
  <riga vuota>  spegne la scritta
  :c <colore>   colore, nome o r,g,b      es.  :c rosso    :c 255,80,0
  :s <n>        velocita' in pixel/frame  es.  :s 2
  :f <n>        fps di rete               es.  :f 25
  :r            inverte la direzione di marcia
  :m            specchia orizzontale (lettere al dritto)
  :v            ribalta sopra/sotto
  :a            appello: chi risponde davvero in rete
  :d            collaudo: ogni pannello mostra il suo numero
  :i            inverti colori (common anode)
  :h            aiuto
  :q            esci

Uso:  python3 TextWall.py            oppure   python3 TextWall.py "CIAO"
"""

import cv2
import numpy as np
import socket
import time
import sys
import glob
import threading
import queue
import os
from collections import deque

import messaggi_watcher

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


# ============================================================
# CONFIGURAZIONE LEDWALL ESP (MULTI-PANNELLO UDP)
# ============================================================
# La POSIZIONE nella lista = la posizione FISICA del pannello sul muro,
# da sinistra a destra. L'indirizzo IP non conta niente.
#
# None = pannello fisicamente presente ma NON raggiungibile in rete.
# La tela viene comunque calcolata sulla larghezza totale del muro: quel
# pezzo di scritta esiste, semplicemente non lo vede nessuno. Cosi' i
# pannelli intorno restano allineati e il giorno che quei due entrano in
# rete basta scriverci l'IP: non cambia nient'altro.
#
# Muro completo: 8 pannelli, 8 ESP, tutti in rete.
# Gli slot 0 e 7 sono le due Wemos D1 mini Pro: se non rispondono restano
# neri e la scritta ci passa sopra senza comparire. UDP non da' errori,
# quindi il sintomo e' solo quello: due pannelli spenti agli estremi.
PANEL_IPS = [   # slot 0  - estrema sinistra   (D1 mini Pro)
    "192.168.1.61",   # slot 1
    "192.168.1.62",   # slot 2
    "192.168.1.63",   # slot 3
    "192.168.1.64",   # slot4
    "192.168.1.65",
    "192.168.1.66",   # slot 5
    "192.168.1.67",   # slot 6
    "192.168.1.68",   # slot 7  - estrema destra     (D1 mini Pro)
]
ESP_PORT = 4210

PANEL_W = 15                        # larghezza di un singolo pannello
PANEL_H = 44                        # altezza di un singolo pannello
WALL_PANELS = len(PANEL_IPS)        # 8 pannelli fisici, accesi o no
WALL_W = PANEL_W * WALL_PANELS      # 120 - larghezza REALE del muro
WALL_H = PANEL_H                    # 44
LIVE_PANELS = [(i, ip) for i, ip in enumerate(PANEL_IPS) if ip]


# ============================================================
# COME COMPORTARSI CON I PANNELLI IRRAGGIUNGIBILI
# ============================================================
# Due ESP non hanno la radio, quindi 30 px della tela non si accenderanno
# mai. Il compositore puo' reagire in tre modi diversi, e la scelta si
# vede parecchio sul muro:
#
#   "fisico"    La tela e' larga 120 come il muro vero. Ogni pannello
#               mostra esattamente il pezzo che gli spetta. La scritta
#               scorre alla velocita' giusta ma SPARISCE mentre attraversa
#               i due pannelli morti, e ricompare dall'altra parte.
#               Corretto dal punto di vista spaziale, illeggibile se il
#               buco e' in mezzo.
#
#   "compatto"  La tela e' larga quanto i soli pannelli vivi (90). Il buco
#               viene saltato: i pannelli dopo mostrano il testo che
#               segue, non quello che gli spetterebbe. Nessun pixel
#               sprecato, ma una lettera puo' finire tagliata a meta' fra
#               due pannelli lontani mezzo metro.
#
#   "contiguo"  Usa solo il blocco piu' lungo di pannelli vivi ATTACCATI
#               fra loro. La scritta e' sempre integra e leggibile.
#               I pannelli vivi rimasti fuori restano spenti sul serio.
#
# Se i due morti stanno a un'estremita' le tre modalita' coincidono.
WALL_LAYOUT = "contiguo"


def build_send_map(layout):
    """Decide quale pezzo di tela va a quale pannello.

    Ritorna (mappa, spenti, larghezza_tela) dove mappa e' una lista di
    (ip, slot_fisico, colonna_iniziale_nella_tela).
    """
    live = LIVE_PANELS

    if layout == "fisico":
        return [(ip, sl, sl * PANEL_W) for sl, ip in live], [], WALL_W

    if layout == "compatto":
        return ([(ip, sl, k * PANEL_W) for k, (sl, ip) in enumerate(live)],
                [], len(live) * PANEL_W)

    if layout == "contiguo":
        best, cur = [], []
        for sl, ip in live:
            cur = cur + [(sl, ip)] if (cur and sl == cur[-1][0] + 1) else [(sl, ip)]
            if len(cur) > len(best):
                best = list(cur)
        usati = {sl for sl, _ in best}
        spenti = [ip for sl, ip in live if sl not in usati]
        return ([(ip, sl, k * PANEL_W) for k, (sl, ip) in enumerate(best)],
                spenti, len(best) * PANEL_W)

    raise ValueError(f"WALL_LAYOUT sconosciuto: {layout!r}")


SEND_MAP, DARK_IPS, CANVAS_W = build_send_map(WALL_LAYOUT)

# Mappa fisica, sempre disponibile: la usa il collaudo :d, che deve poter
# accendere ogni pannello al suo posto vero a prescindere dal layout.
PHYS_MAP = [(ip, sl, sl * PANEL_W) for sl, ip in LIVE_PANELS]

# --- Orientamento dell'immagine sul muro ---------------------------------
# MIRROR_X ribalta la tela da sinistra a destra. Serve quando il muro e'
# cablato al contrario e le lettere escono specchiate.
# Attenzione: specchiare da solo invertirebbe anche il senso di marcia,
# quindi quando e' attivo lo scorrimento viene automaticamente invertito
# per compensare. Risultato: lettere dritte, direzione invariata.
MIRROR_X = True                   # toggle con :m
FLIP_Y = False                    # ribalta sopra/sotto, toggle con :v

# Verso in cui la scritta viaggia SUL MURO, cioe' quello che vedi tu.
# Lo specchio non c'entra: e' gia' compensato piu' sotto.
#   +1  la scritta entra da destra e se ne va a sinistra (marquee classico)
#   -1  la scritta entra da sinistra e se ne va a destra
SCROLL_DIR = -1                   # toggle con :r

ESP_SERPENTINE_HORIZONTAL = True  # righe dispari cablate al contrario
ESP_START_BOTTOM = False          # False = data-in in alto a sinistra

# Pausa tra un pannello e l'altro, per non ingolfare il router.
# Occhio al budget: 8 pannelli x 3 ms = 24 ms fissi per frame, contro i
# 33 ms di periodo a 30 fps. Ci sta, ma e' stretto: se vuoi salire di fps
# questo e' il primo numero da abbassare.
ESP_PANEL_GAP = 0.003

# --- Spezzatura in 2 pacchetti -------------------------------------------
# NON usare len(dati)//2: funzionerebbe solo per caso. La spezzatura deve
# cadere su un confine di RIGA, altrimenti si taglia un pixel a meta'.
# 22 righe x 15 px x 3 byte = 990 byte, + 1 byte di indice = 991 byte,
# comodamente sotto l'MTU UDP (~1472) quindi niente frammentazione IP.
assert PANEL_H % 2 == 0, "PANEL_H deve essere pari per spezzare in 2 pacchetti uguali"
ROWS_PER_PACKET = PANEL_H // 2
BYTES_PER_PACKET = ROWS_PER_PACKET * PANEL_W * 3


# ============================================================
# CONFIGURAZIONE ARDUINO (SERIALE) - secondario
# ============================================================
ARDUINO_ENABLED = False           # metti True se hai anche il muro seriale collegato
ARDUINO_PORT = "auto"
ARDUINO_BAUD = 500000
ARD_COLS = 56                     # 7 pannelli da 8
ARD_ROWS = 32
ARD_PANEL_W = 8
ARD_PANEL_H = 32
ARD_PANELS = 7
ARD_PANEL_ORDER = [6, 5, 4, 3, 2, 1, 0]          # 0 = estrema destra
ARD_PANEL_START_BOTTOM = [False] * 7
ARD_SERPENTINE_X = True
ARD_FLIP_V = True                 # pannelli montati a testa in giu'
ARD_MAGIC = b'\xFF\x4C\x45'


# ============================================================
# RESA COLORE
# ============================================================
GAMMA = 2.5
COMMON_ANODE = False              # toggle con :i

GAMMA_LUT = np.array([((i / 255.0) ** GAMMA) * 255
                      for i in np.arange(0, 256)]).astype(np.uint8)


# ============================================================
# TESTO
# ============================================================
FONT = cv2.FONT_HERSHEY_DUPLEX
TEXT_FILL = 0.50                  # altezza glifi rispetto all'altezza del muro
SCROLL_SPEED = 1.0                # pixel per frame
NET_FPS = 30                      # frame al secondo spediti in rete

# Due colori indipendenti: le lettere e il fondo.
# La maschera del testo fa da fusione fra i due, quindi qualsiasi
# combinazione e' possibile senza modalita' speciali:
#   fondo nero  + lettere colorate  = scritta normale
#   fondo acceso + lettere nere     = stencil
#   fondo bianco + lettere rosse    = quello impostato qui sotto
TEXT_COLOR = (255, 255, 255)          # lettere, cambia con :c
BG_COLOR = (0, 0, 0)            # sfondo,  cambia con :b

COLORI = {
    'bianco':    (255, 255, 255),
    'rosso':     (255, 0, 0),
    'verde':     (0, 255, 0),
    'blu':       (0, 0, 255),
    'giallo':    (255, 255, 0),
    'ciano':     (0, 255, 255),
    'magenta':   (255, 0, 255),
    'arancione': (255, 120, 0),
    'viola':     (150, 0, 255),
    'rosa':      (255, 60, 140),
    'ambra':     (255, 170, 0),
    'nero':      (0, 0, 0),
}


# ============================================================
# MESSAGGI AUTOMATICI (dal bridge via Bluetooth)
# ============================================================
CARTELLA_MESSAGGI = os.path.dirname(os.path.abspath(__file__))
FILE_MOSTRATI = os.path.join(CARTELLA_MESSAGGI, "mostrati.jsonl")
DURATA_MESSAGGIO_AUTO = 8.0       # secondi di permanenza di ogni messaggio
INTERVALLO_CONTROLLO_CARTELLA = 2.0   # ogni quanto guardare la cartella
IDLE_TIMEOUT_MANUALE = 15.0       # secondi dopo l'ultimo input da tastiera


# ============================================================
# PREVIEW
# ============================================================
PREVIEW = True
PREVIEW_ZOOM = 10                 # 90x44 -> 900x440


# ============================================================
# RENDERING TESTO
# ============================================================

def render_text_mask(text, height):
    """Disegna il testo in bianco su nero e ritorna la sola maschera 2D.

    Tenere la maschera separata dal colore permette di cambiare tinta o
    passare in negativo senza ridisegnare niente: si ricolora al volo.
    """
    target = max(8, int(round(height * TEXT_FILL)))
    thick = max(1, int(round(target / 16.0)))

    # Misura a scala 1.0, poi ricava la scala che porta i glifi a `target` px
    (_, h0), _ = cv2.getTextSize(text, FONT, 1.0, thick)
    scale = target / float(max(1, h0))
    (tw, th), base = cv2.getTextSize(text, FONT, scale, thick)

    # Disegna su una tela abbondante e poi ritaglia l'inchiostro vero.
    # Centrare sulla bounding box reale e' l'unico modo di stare davvero in
    # mezzo ai 44 px con maiuscole, accenti e discendenti insieme: le
    # metriche del font riservano sempre spazio al discendente anche in
    # "CIAO", e la scritta finirebbe 3-4 px troppo in alto.
    pad = height
    big = np.zeros((th + base + 2 * pad, max(1, tw) + 2 * pad), np.uint8)
    cv2.putText(big, text, (pad, pad + th), FONT, scale, 255, thick, cv2.LINE_AA)

    ys, xs = np.nonzero(big)
    if len(ys) == 0:
        return np.zeros((height, 1), np.uint8)
    ink = big[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    # Se l'inchiostro sfora comunque l'altezza del muro, rimpicciolisci
    if ink.shape[0] > height:
        f = height / float(ink.shape[0])
        ink = cv2.resize(ink, (max(1, int(round(ink.shape[1] * f))), height),
                         interpolation=cv2.INTER_AREA)

    side = max(2, height // 8)
    out = np.zeros((height, ink.shape[1] + 2 * side), np.uint8)
    top = (height - ink.shape[0]) // 2
    out[top:top + ink.shape[0], side:side + ink.shape[1]] = ink
    return out


def colora(mask, fg, bg=(0, 0, 0)):
    """Da maschera 2D a immagine RGB, fondendo due colori.

    La maschera vale 0 sul fondo e 255 sul pieno delle lettere, con i
    valori intermedi sui bordi antialiasati. Usandola come peso di una
    fusione fra `bg` e `fg`, i contorni sfumano da un colore all'altro
    invece di essere seghettati: vale anche quando il fondo e' acceso e
    le lettere sono spente.
    """
    a = mask.astype(np.int32)[..., None]
    f = np.asarray(fg, np.int32)
    b = np.asarray(bg, np.int32)
    return ((b * (255 - a) + f * a) // 255).astype(np.uint8)


def render_text(text, height, color_rgb):
    """Striscia RGB con il testo acceso su fondo spento (usata dal collaudo)."""
    return colora(render_text_mask(text, height), color_rgb)


SLOT_COLORS = [(255, 0, 0), (255, 140, 0), (255, 255, 0), (0, 255, 0),
               (0, 255, 255), (0, 80, 255), (180, 0, 255), (255, 255, 255)]


def make_id_canvas():
    """Tela di collaudo: ogni slot mostra il proprio numero, con un colore suo.

    Serve a scoprire QUALE ESP sta fisicamente DOVE. Accendi il muro, leggi
    i numeri da sinistra a destra e riordina PANEL_IPS di conseguenza.
    Uno slot che resta nero e' un pannello non raggiungibile (None nella
    lista) oppure una scheda che non risponde: nel terminale c'e' scritto
    quale delle due.
    """
    canvas = np.zeros((WALL_H, WALL_W, 3), np.uint8)

    for slot in range(WALL_PANELS):
        colore = SLOT_COLORS[slot % len(SLOT_COLORS)]
        x0 = slot * PANEL_W

        # Fondo appena acceso: distingue "pannello vivo ma vuoto" da "morto"
        canvas[:, x0:x0 + PANEL_W] = tuple(c // 12 for c in colore)

        cifra = render_text(str(slot), PANEL_H, colore)
        # Rimpicciolisci finche' la cifra non entra nei 15 px del pannello
        if cifra.shape[1] > PANEL_W:
            f = (PANEL_W - 2) / float(cifra.shape[1])
            cifra = cv2.resize(cifra, (PANEL_W - 2, max(1, int(round(cifra.shape[0] * f)))),
                               interpolation=cv2.INTER_AREA)

        h, w = cifra.shape[:2]
        y = (WALL_H - h) // 2
        x = x0 + (PANEL_W - w) // 2
        # max: la cifra si somma al fondo invece di cancellarlo
        canvas[y:y + h, x:x + w] = np.maximum(canvas[y:y + h, x:x + w], cifra)

    return canvas


class Marquee:
    """Scritta scorrevole in loop su una tela larga `width` e alta `height`.

    Costruisce una striscia [testo][spazio vuoto] e ci fa scorrere sopra
    una finestra larga quanto il muro, con wrap-around: il testo esce a
    sinistra e rientra da destra senza salti.
    """

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.strip = None          # maschera 2D, non RGB
        self.fg = TEXT_COLOR
        self.bg = BG_COLOR
        self.total = 0
        self.off = 0.0
        self.blank = np.zeros((height, width, 3), np.uint8)

    def set_colors(self, fg=None, bg=None):
        """Cambia tinta senza ridisegnare e senza far saltare la posizione."""
        if fg is not None:
            self.fg = fg
        if bg is not None:
            self.bg = bg

    def set_text(self, text):
        if not text:
            self.strip = None
            return
        body = render_text_mask(text, self.h)
        # Lo spazio vuoto e' maschera a zero: in negativo diventa fondo
        # acceso, quindi fra una ripetizione e l'altra il muro resta pieno.
        gap = np.zeros((self.h, self.w + 6), np.uint8)
        self.strip = np.hstack([body, gap])
        self.total = self.strip.shape[1]
        # Parti dalla coda dello spazio vuoto: il testo entra da destra
        self.off = float(self.total - self.w)

    def clear(self):
        self.strip = None

    def step(self, speed):
        if self.strip is None:
            return
        self.off = (self.off + speed) % self.total

    def frame(self):
        # Nessun testo = muro spento, anche in stencil: la riga vuota deve
        # spegnere, non accendere tutto.
        if self.strip is None:
            return self.blank
        idx = (np.arange(self.w) + int(self.off)) % self.total
        return colora(self.strip[:, idx], self.fg, self.bg)


# ============================================================
# USCITA ESP (UDP)
# ============================================================

def create_udp_socket():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[OK] Socket UDP porta {ESP_PORT} -> "
              f"{len(LIVE_PANELS)}/{WALL_PANELS} pannelli raggiungibili")
        for slot, ip in enumerate(PANEL_IPS):
            x0, x1 = slot * PANEL_W, (slot + 1) * PANEL_W - 1
            stato = ip if ip else "--- non in rete, resta spento ---"
            print(f"     slot {slot}  colonne {x0:3d}-{x1:3d}   {stato}")
        return sock
    except Exception as e:
        print(f"[X] Errore creazione socket UDP: {e}")
        return None


def applica_orientamento(canvas):
    """Ribalta la tela secondo MIRROR_X / FLIP_Y, appena prima di spedirla.

    Si fa QUI e non nel renderer del testo cosi' vale per tutto quello che
    finisce sul muro, collaudo :d compreso.
    """
    if MIRROR_X:
        canvas = canvas[:, ::-1]
    if FLIP_Y:
        canvas = canvas[::-1, :]
    return np.ascontiguousarray(canvas)


def appello(sock, attesa=1.5):
    """Chiede a tutti gli ESP di farsi vivi, e confronta con PANEL_IPS.

    Manda un pacchetto corto che comincia con 0xFF (un frame vero e' lungo
    991 byte e comincia con 0 o 1, quindi non si confondono). Ogni scheda
    risponde con il suo indirizzo, il suo MAC e la potenza del segnale.
    Richiede il firmware con la scoperta attiva.
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    bcast = ".".join(LIVE_PANELS[0][1].split(".")[:3] + ["255"])

    for _ in range(2):
        for dest in [bcast] + [ip for _, ip in LIVE_PANELS]:
            try:
                sock.sendto(b'\xFFWHO', (dest, ESP_PORT))
            except Exception:
                pass

    trovati = {}
    sock.settimeout(0.25)
    scadenza = time.time() + attesa
    while time.time() < scadenza:
        try:
            dati, mitt = sock.recvfrom(256)
        except (socket.timeout, OSError):
            continue
        if dati[:1] == b'\xFE':
            trovati[mitt[0]] = dati[1:].decode("ascii", "replace")
    sock.settimeout(None)

    print(f"\n[APPELLO] {len(trovati)} schede hanno risposto:")
    per_mac = {}
    for slot, ip in enumerate(PANEL_IPS):
        if not ip:
            continue
        info = trovati.pop(ip, None)
        if info:
            campi = dict(c.split("=", 1) for c in info.split(";") if "=" in c)
            mac = campi.get("mac", "?")
            per_mac.setdefault(mac, []).append(ip)
            print(f"   slot {slot}  {ip:<16} ok    rssi {campi.get('rssi','?'):>4} dBm  {mac}")
        else:
            print(f"   slot {slot}  {ip:<16} MUTA  nessuna risposta")

    for ip, info in trovati.items():
        print(f"   ???      {ip:<16} risponde ma non e' in PANEL_IPS -> {info}")

    doppi = {m: ips for m, ips in per_mac.items() if len(ips) > 1}
    for mac, ips in doppi.items():
        print(f"   >>> {' e '.join(ips)} sono la STESSA scheda ({mac})")
    if not doppi and len(per_mac) == len(LIVE_PANELS):
        print("   tutte distinte, rete a posto.")
    return trovati


def send_esp(sock, canvas_rgb, mappa=None):
    """Affetta la tela e spedisce 2 pacchetti a ogni pannello della mappa."""
    if mappa is None:
        mappa = SEND_MAP
    frame = GAMMA_LUT[canvas_rgb]
    if COMMON_ANODE:
        frame = 255 - frame

    for ip, _slot, x0 in mappa:
        fetta = frame[:, x0:x0 + PANEL_W].copy()

        if ESP_START_BOTTOM:
            fetta = fetta[::-1, :, :]
        if ESP_SERPENTINE_HORIZONTAL:
            fetta[1::2] = fetta[1::2, ::-1, :].copy()

        raw = fetta.tobytes()
        try:
            sock.sendto(b'\x00' + raw[:BYTES_PER_PACKET], (ip, ESP_PORT))
            sock.sendto(b'\x01' + raw[BYTES_PER_PACKET:], (ip, ESP_PORT))
            time.sleep(ESP_PANEL_GAP)
        except Exception:
            pass


def blank_panels(sock, ips):
    """Spegne davvero i pannelli vivi che il layout non usa: senza questo
    resterebbero congelati sull'ultimo frame ricevuto."""
    nero = bytes(PANEL_W * PANEL_H * 3)
    for ip in ips:
        try:
            sock.sendto(b'\x00' + nero[:BYTES_PER_PACKET], (ip, ESP_PORT))
            sock.sendto(b'\x01' + nero[BYTES_PER_PACKET:], (ip, ESP_PORT))
        except Exception:
            pass


def blackout_esp_all(sock):
    nero = bytes(PANEL_W * PANEL_H * 3)
    for _, ip in LIVE_PANELS:
        try:
            sock.sendto(b'\x00' + nero[:BYTES_PER_PACKET], (ip, ESP_PORT))
            sock.sendto(b'\x01' + nero[BYTES_PER_PACKET:], (ip, ESP_PORT))
            time.sleep(0.02)
        except Exception:
            pass


# ============================================================
# USCITA ARDUINO (SERIALE)
# ============================================================

def build_arduino_index_map():
    """Permutazione pixel-immagine -> pixel-catena, calcolata una volta sola.

    Ogni pannello e' 8x32, il segnale entra in alto a sinistra e fa zigzag
    orizzontale. ARD_PANEL_ORDER dice quale posizione X occupa il pannello
    n-esimo della catena.
    """
    idx = np.empty(ARD_COLS * ARD_ROWS, dtype=np.int32)
    k = 0
    for p in range(ARD_PANELS):
        start_x = ARD_PANEL_ORDER[p] * ARD_PANEL_W
        bottom = ARD_PANEL_START_BOTTOM[p]
        for y_local in range(ARD_PANEL_H):
            gy = (ARD_PANEL_H - 1 - y_local) if bottom else y_local
            for x_local in range(ARD_PANEL_W):
                if ARD_SERPENTINE_X and (y_local % 2 == 1):
                    ex = ARD_PANEL_W - 1 - x_local
                else:
                    ex = x_local
                idx[k] = gy * ARD_COLS + (start_x + ex)
                k += 1
    return idx


ARD_INDEX = build_arduino_index_map()


def create_arduino_serial():
    if not ARDUINO_ENABLED:
        return None
    if not HAS_SERIAL:
        print("[!] pyserial non installato -> Arduino disabilitato (pip install pyserial)")
        return None

    port = ARDUINO_PORT
    if port == "auto":
        # Solo porte USB reali: niente /dev/tty.* generico, che su macOS
        # pesca anche le seriali Bluetooth e blocca l'apertura.
        trovate = (glob.glob('/dev/cu.usbmodem*') + glob.glob('/dev/cu.usbserial*') +
                   glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
        if not trovate:
            print("[!] Nessuna porta seriale USB trovata -> Arduino disabilitato")
            return None
        port = trovate[0]
        print(f"[AUTO] Porta seriale: {port}")

    try:
        ser = serial.Serial(port, ARDUINO_BAUD, timeout=0.01)
        time.sleep(2)  # attesa reset scheda
        ser.reset_input_buffer()
        print(f"[OK] Arduino su {port} @ {ARDUINO_BAUD} baud - {ARD_COLS}x{ARD_ROWS}")
        return ser
    except Exception as e:
        print(f"[X] Arduino non connesso: {e}")
        return None


def send_arduino(ser, canvas_rgb):
    """Manda una tela 56x32 gia' renderizzata: gamma, flip, rimappa, spedisci."""
    frame = GAMMA_LUT[canvas_rgb]
    if COMMON_ANODE:
        frame = 255 - frame
    if ARD_FLIP_V:
        frame = frame[::-1, :, :]
    payload = frame.reshape(-1, 3)[ARD_INDEX].tobytes()
    ser.write(ARD_MAGIC + payload)


# ============================================================
# INPUT DA TERMINALE (thread separato, non blocca il rendering)
# ============================================================

def input_worker(q):
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            q.put(None)
            return
        q.put(line)


def parse_color(arg):
    arg = arg.strip().lower()
    if arg in COLORI:
        return COLORI[arg]
    parts = arg.replace(';', ',').split(',')
    if len(parts) == 3:
        try:
            return tuple(max(0, min(255, int(p))) for p in parts)
        except ValueError:
            pass
    return None


HELP = """
  <testo>       manda la scritta
  <riga vuota>  spegne la scritta
  :c <colore>   colore delle LETTERE
  :b <colore>   colore dello SFONDO   (:b nero = scritta classica)
                bianco rosso verde blu giallo ciano magenta arancione
                viola rosa ambra nero, oppure r,g,b
  :n            scambia lettere e sfondo
  :s <n>        velocita' in pixel/frame (es. :s 2)
  :f <n>        fps di rete (es. :f 25)
  :r            inverte la direzione di marcia
  :m            specchia orizzontale (lettere al dritto)
  :v            ribalta sopra/sotto
  :a            appello: chi risponde davvero in rete
  :d            collaudo: ogni pannello mostra il suo numero
  :i            inverti colori (common anode)
  :h            questo aiuto
  :q            esci
"""


# ============================================================
# MAIN
# ============================================================

def main():
    global COMMON_ANODE, MIRROR_X, FLIP_Y, SCROLL_DIR

    speed = SCROLL_SPEED
    fps = NET_FPS
    fg, bg = TEXT_COLOR, BG_COLOR
    testo = sys.argv[1] if len(sys.argv) > 1 else ""

    coda_auto = deque()
    ultimo_input_manuale = 0.0
    inizio_messaggio_corrente = None
    ultimo_controllo_cartella = 0.0

    print("\n" + "=" * 56)
    print("  TEXTWALL - scritta scorrevole")
    print(f"  Muro    : {WALL_PANELS} pannelli {PANEL_W}x{PANEL_H} -> tela {WALL_W}x{WALL_H}")
    print(f"  In rete : {len(LIVE_PANELS)} su {WALL_PANELS}")
    usati = [sl for _, sl, _ in SEND_MAP]
    print(f"  Layout  : {WALL_LAYOUT} -> tela {CANVAS_W}x{WALL_H}, slot {usati}")
    if DARK_IPS:
        print(f"            {len(DARK_IPS)} pannello/i vivo/i tenuto/i spento/i: "
              f"{', '.join(DARK_IPS)}")
    print(f"            {PANEL_W*PANEL_H} LED/pannello, {PANEL_W*PANEL_H*3} byte")
    print(f"            2 pacchetti da {BYTES_PER_PACKET + 1} byte ({ROWS_PER_PACKET} righe l'uno)")
    if ARDUINO_ENABLED:
        print(f"  Arduino : {ARD_COLS}x{ARD_ROWS} seriale")
    print("=" * 56)

    sock = create_udp_socket()
    ser = create_arduino_serial()

    if sock is None and ser is None:
        print("[X] Nessuna uscita disponibile.")
        return

    wall = Marquee(CANVAS_W, WALL_H)
    ard = Marquee(ARD_COLS, ARD_ROWS) if ser else None

    wall.set_colors(fg, bg)
    if ard:
        ard.set_colors(fg, bg)
    if testo:
        wall.set_text(testo)
        if ard:
            ard.set_text(testo)

    if PREVIEW:
        cv2.namedWindow('TextWall', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('TextWall', WALL_W * PREVIEW_ZOOM, WALL_H * PREVIEW_ZOOM)

    q = queue.Queue()
    threading.Thread(target=input_worker, args=(q,), daemon=True).start()

    print(HELP)
    print("Scrivi qualcosa e premi Invio:\n")

    id_mode = False
    ID_CANVAS = make_id_canvas()

    if sock is not None:
        appello(sock)

    # Handshake Arduino: parte pronto, poi aspetta la 'K' di conferma
    ard_ready = True
    ard_last = time.time()

    periodo = 1.0 / fps
    t_next = time.time()

    try:
        while True:
            # --- comandi dal terminale ---
            while not q.empty():
                line = q.get()
                if line is None:
                    raise KeyboardInterrupt

                ultimo_input_manuale = time.time()

                s = line.strip()
                if s.startswith(':'):
                    cmd = s[1:2].lower()
                    arg = s[2:].strip()

                    if cmd == 'q':
                        raise KeyboardInterrupt
                    elif cmd == 'h':
                        print(HELP)
                    elif cmd == 'i':
                        COMMON_ANODE = not COMMON_ANODE
                        print(f"[TOGGLE] Inversione: {'ATTIVA' if COMMON_ANODE else 'off'}")
                    elif cmd == 'n':
                        fg, bg = bg, fg
                        wall.set_colors(fg, bg)
                        if ard:
                            ard.set_colors(fg, bg)
                        print(f"[SCAMBIO] lettere {fg}  sfondo {bg}")
                    elif cmd == 'r':
                        SCROLL_DIR = -SCROLL_DIR
                        verso = ("da destra verso sinistra" if SCROLL_DIR > 0
                                 else "da sinistra verso destra")
                        print(f"[DIREZIONE] {verso}")
                    elif cmd == 'm':
                        MIRROR_X = not MIRROR_X
                        print(f"[SPECCHIO] orizzontale: "
                              f"{'ATTIVO' if MIRROR_X else 'off'}"
                              f"  (direzione compensata)")
                    elif cmd == 'v':
                        FLIP_Y = not FLIP_Y
                        print(f"[SPECCHIO] verticale: {'ATTIVO' if FLIP_Y else 'off'}")
                    elif cmd == 'a':
                        if sock is not None:
                            appello(sock)
                    elif cmd == 'd':
                        id_mode = not id_mode
                        if id_mode:
                            print("[ID] Collaudo pannelli. Leggi i numeri sul muro")
                            print("     da sinistra a destra e confrontali con questa lista:")
                            for sl, pip in enumerate(PANEL_IPS):
                                print(f"       {sl}  {pip if pip else '(non in rete)'}")
                            print("     Se i numeri non sono in ordine, riordina PANEL_IPS.")
                        else:
                            print("[ID] Collaudo chiuso.")
                    elif cmd in ('c', 'b'):
                        c = parse_color(arg)
                        if c is None:
                            print(f"[!] Colore '{arg}' non riconosciuto")
                        elif cmd == 'c':
                            fg = c
                            wall.set_colors(fg=fg)
                            if ard:
                                ard.set_colors(fg=fg)
                            print(f"[COLORE] lettere {fg}")
                        else:
                            bg = c
                            wall.set_colors(bg=bg)
                            if ard:
                                ard.set_colors(bg=bg)
                            print(f"[COLORE] sfondo {bg}")
                    elif cmd == 's':
                        try:
                            speed = max(0.1, float(arg.replace(',', '.')))
                            print(f"[VELOCITA] {speed} px/frame")
                        except ValueError:
                            print("[!] Uso: :s 2")
                    elif cmd == 'f':
                        try:
                            fps = max(1, min(60, int(arg)))
                            periodo = 1.0 / fps
                            print(f"[FPS] {fps}")
                        except ValueError:
                            print("[!] Uso: :f 25")
                    else:
                        print(f"[!] Comando ':{cmd}' sconosciuto. :h per l'aiuto")
                else:
                    testo = s
                    wall.set_text(testo)
                    if ard:
                        ard.set_text(testo)
                    print(f"[WALL] {testo!r}" if testo else "[WALL] spento")

            # --- messaggi automatici dal bridge (Bluetooth) ---
            ora = time.time()
            if ora - ultimo_controllo_cartella >= INTERVALLO_CONTROLLO_CARTELLA:
                try:
                    nuovi = messaggi_watcher.elabora_cartella(CARTELLA_MESSAGGI, FILE_MOSTRATI)
                    coda_auto.extend(nuovi)
                except Exception as e:
                    print(f"\n[X] Errore lettura cartella messaggi: {e}")
                ultimo_controllo_cartella = ora

            prossimo = messaggi_watcher.prossimo_testo_automatico(
                coda_auto, ultimo_input_manuale, inizio_messaggio_corrente, ora,
                IDLE_TIMEOUT_MANUALE, DURATA_MESSAGGIO_AUTO,
            )
            if prossimo is not None:
                testo = prossimo["text"]
                wall.set_text(testo)
                if ard:
                    ard.set_text(testo)
                inizio_messaggio_corrente = ora
                print(f"[AUTO] {testo!r}")

            # --- avanza e componi ---
            # Il passo tiene conto di due cose insieme: il verso che vuoi
            # vedere sul muro (SCROLL_DIR) e lo specchio, che da solo
            # invertirebbe la marcia e quindi va compensato.
            passo = speed * SCROLL_DIR * (-1 if MIRROR_X else 1)
            wall.step(passo)
            if sock is not None:
                if id_mode:
                    # Collaudo: mappa FISICA, ogni pannello al suo posto vero
                    canvas = applica_orientamento(ID_CANVAS)
                    send_esp(sock, canvas, PHYS_MAP)
                else:
                    canvas = applica_orientamento(wall.frame())
                    send_esp(sock, canvas)
                    if DARK_IPS:
                        blank_panels(sock, DARK_IPS)
            else:
                canvas = applica_orientamento(ID_CANVAS if id_mode else wall.frame())

            if ser is not None:
                ard.step(speed)
                try:
                    if ser.in_waiting > 0 and b'K' in ser.read_all():
                        ard_ready = True
                except OSError:
                    print("\n[!] Cavo Arduino scollegato.")
                    ser = None
                    ard = None

                if ser is not None:
                    # Sblocco di sicurezza se la 'K' si e' persa
                    if not ard_ready and (time.time() - ard_last > 0.5):
                        ard_ready = True
                    if ard_ready:
                        try:
                            send_arduino(ser, applica_orientamento(ard.frame()))
                            ard_ready = False
                            ard_last = time.time()
                        except Exception as e:
                            print(f"\n[X] Errore invio Arduino: {e}")
                            ser = None
                            ard = None

            # --- anteprima ---
            if PREVIEW:
                big = cv2.resize(canvas, (canvas.shape[1] * PREVIEW_ZOOM,
                                          WALL_H * PREVIEW_ZOOM),
                                 interpolation=cv2.INTER_NEAREST)
                cv2.imshow('TextWall', cv2.cvtColor(big, cv2.COLOR_RGB2BGR))
                k = cv2.waitKey(1) & 0xFF
                if k == ord('q') or k == 27:
                    break

            # --- pacing ---
            t_next += periodo
            dt = t_next - time.time()
            if dt > 0:
                time.sleep(dt)
            else:
                t_next = time.time()

    except KeyboardInterrupt:
        pass

    finally:
        print("\n[LED] Spegnimento...")
        if PREVIEW:
            cv2.destroyAllWindows()
        if sock is not None:
            blackout_esp_all(sock)
            sock.close()
            print("[OK] ESP spenti, socket chiuso.")
        if ser is not None:
            try:
                ser.write(ARD_MAGIC + bytes(ARD_COLS * ARD_ROWS * 3))
                time.sleep(0.1)
                ser.close()
                print("[OK] Arduino spento, seriale chiusa.")
            except Exception:
                pass
        print("[BYE]\n")


if __name__ == "__main__":
    main()
