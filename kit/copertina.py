"""Passo 8: la copertina della puntata.

Stile fisso, quello delle copertine attuali del podcast: fondo blu
notte con una griglia appena visibile, al centro un'icona disegnata a
linee arancioni luminose che fa capire l'argomento. Nessun testo.

Due modi:
  gemini   un modello d'immagine disegna l'icona richiesta dalla scheda
           (soggetto_immagine), dentro lo stile fisso;
  disegno  il programma disegna da solo un'icona scelta dal tema
           (onde, occhio, documento, finestra, strati, rete, grafico,
           orbite). Serve da riserva se il modello non risponde.
"""
import hashlib
import io
import math
import random
import re

from PIL import Image, ImageDraw, ImageFilter

TEMI = [
    ("onde",     r"audio|voce|voice|speech|parlat|music|sound|suono|ascolt"),
    ("occhio",   r"video|vision|visiv|camera|guard|stream"),
    ("finestra", r"immagin|image|pixel|foto|disegn|grafic|render|agent|computer|interfacc|gui|browser|web"),
    ("documento", r"testo|text|linguag|language|parol|llm|token|scritt|lettur|document|traduz"),
    ("strati",   r"memori|ricord|memory|context|contest|cache|dati|data"),
    ("rete",     r"rete|grafo|graph|network|connession|relazion|conoscenz|knowledge"),
    ("grafico",  r"ragion|reason|matemat|math|logic|calcol|benchmark|valutaz|risultat|scal"),
    ("codice",   r"codice|code|program|software|robot|strument|tool"),
]


def tema(*testi):
    t = " ".join(x for x in testi if x).lower()
    punteggi = [(len(re.findall(rx, t)), nome) for nome, rx in TEMI]
    migliore = max(punteggi)
    return migliore[1] if migliore[0] else "orbite"


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _fondo(L, P):
    img = Image.new("RGB", (L, L), P["fondo"])
    d = ImageDraw.Draw(img)
    passo = L // 16
    for i in range(0, L + 1, passo):
        d.line([(i, 0), (i, L)], fill=P["griglia"], width=max(1, L // 900))
        d.line([(0, i), (L, i)], fill=P["griglia"], width=max(1, L // 900))
    # vignettatura: bordi un po' più scuri, centro un po' più chiaro
    alone = Image.new("L", (L, L), 0)
    ImageDraw.Draw(alone).ellipse([L * 0.15, L * 0.15, L * 0.85, L * 0.85], fill=60)
    alone = alone.filter(ImageFilter.GaussianBlur(L // 8))
    chiaro = Image.new("RGB", (L, L), P["griglia"])
    return Image.composite(chiaro, img, alone)


def _icona(d, motivo, L, rng, w, punti):
    """Disegna l'icona in un riquadro centrale. punti: lista dove segnare i nodi luminosi."""
    c = L / 2
    R = L * 0.24                      # mezza dimensione del riquadro dell'icona
    x0, y0, x1, y1 = c - R, c - R, c + R, c + R

    def finestra(alto=0.0):
        d.rounded_rectangle([x0, y0 + alto, x1, y1], radius=L * 0.012, width=w)
        d.line([(x0, y0 + alto + R * 0.18), (x1, y0 + alto + R * 0.18)], width=w)
        for k in range(3):
            punti.append((x0 + R * (0.09 + 0.09 * k), y0 + alto + R * 0.09, w * 0.9))

    if motivo == "onde":
        n = 21
        for k in range(n):
            x = x0 + (x1 - x0) * k / (n - 1)
            h = R * (0.15 + 0.85 * abs(math.sin(k * 0.55 + rng.uniform(0, 0.4))) * math.sin(math.pi * k / (n - 1)))
            d.line([(x, c - h), (x, c + h)], width=w)
    elif motivo == "occhio":
        pts_su = [(x0 + (x1 - x0) * t / 40, c - R * 0.55 * math.sin(math.pi * t / 40)) for t in range(41)]
        pts_giu = [(x, 2 * c - y) for x, y in pts_su]
        d.line(pts_su, width=w)
        d.line(pts_giu, width=w)
        d.ellipse([c - R * 0.32, c - R * 0.32, c + R * 0.32, c + R * 0.32], width=w)
        d.ellipse([c - R * 0.1, c - R * 0.1, c + R * 0.1, c + R * 0.1], width=w)
        punti.append((c + R * 0.12, c - R * 0.12, w * 1.4))
    elif motivo == "finestra":
        finestra()
        g = 6
        for k in range(1, g):
            x = x0 + (x1 - x0) * k / g
            y = y0 + R * 0.18 + (y1 - y0 - R * 0.18) * k / g
            d.line([(x, y0 + R * 0.18), (x, y1)], width=max(1, w // 2))
            d.line([(x0, y), (x1, y)], width=max(1, w // 2))
        q = R * 0.38
        d.rectangle([c - q, c - q * 0.7, c + q, c + q * 1.1], width=w)
        d.ellipse([c - q * 0.25, c - q * 0.35, c + q * 0.25, c + q * 0.15], width=w)
        d.line([(c - q, c + q * 0.8), (c - q * 0.2, c + q * 0.25), (c + q * 0.3, c + q * 0.6), (c + q, c + q * 0.3)], width=w)
        for (a, b) in ((c - q, c - q * 0.7), (c + q, c - q * 0.7), (c - q, c + q * 1.1), (c + q, c + q * 1.1)):
            punti.append((a, b, w * 1.2))
    elif motivo == "documento":
        piega = R * 0.35
        d.line([(x0 + R * 0.2, y0), (x1 - piega, y0), (x1, y0 + piega), (x1, y1), (x0 + R * 0.2, y1),
                (x0 + R * 0.2, y0)], width=w, joint="curve")
        d.line([(x1 - piega, y0), (x1 - piega, y0 + piega), (x1, y0 + piega)], width=w)
        for k in range(6):
            y = y0 + R * 0.55 + k * R * 0.22
            lung = (x1 - x0 - R * 0.6) * rng.uniform(0.55, 1.0)
            d.line([(x0 + R * 0.45, y), (x0 + R * 0.45 + lung, y)], width=w)
    elif motivo == "strati":
        for k in range(4):
            dy = (k - 1.5) * R * 0.38
            a = [(c, c + dy - R * 0.32), (c + R * 0.95, c + dy), (c, c + dy + R * 0.32), (c - R * 0.95, c + dy)]
            d.polygon(a, outline=None)
            d.line(a + [a[0]], width=w, joint="curve")
    elif motivo == "rete":
        nodi = [(c, c)] + [(c + R * 0.85 * math.cos(a), c + R * 0.85 * math.sin(a))
                           for a in [i * 2 * math.pi / 6 + rng.uniform(-0.2, 0.2) for i in range(6)]]
        for p in nodi[1:]:
            d.line([nodi[0], p], width=w)
        for i in range(1, 7):
            d.line([nodi[i], nodi[i % 6 + 1]], width=max(1, w // 2))
        for i, (x, y) in enumerate(nodi):
            r = R * (0.13 if i == 0 else 0.08)
            d.ellipse([x - r, y - r, x + r, y + r], width=w)
            punti.append((x, y, w * 0.9))
    elif motivo == "grafico":
        d.line([(x0, y0), (x0, y1), (x1, y1)], width=w)
        n = 5
        for k in range(n):
            h = (y1 - y0) * (0.25 + 0.65 * (k + 1) / n) * rng.uniform(0.85, 1.0)
            xa = x0 + R * 0.25 + k * (x1 - x0 - R * 0.3) / n
            d.rectangle([xa, y1 - h, xa + R * 0.22, y1], width=w)
        d.line([(x0 + R * 0.2, y1 - R * 0.4), (x1 - R * 0.1, y0 + R * 0.15)], width=w)
        punti.append((x1 - R * 0.1, y0 + R * 0.15, w * 1.6))
    elif motivo == "codice":
        finestra()
        s = R * 0.35
        d.line([(c - s * 0.4, c - s * 0.3), (c - s * 1.3, c + s * 0.3), (c - s * 0.4, c + s * 0.9)], width=w)
        d.line([(c + s * 0.4, c - s * 0.3), (c + s * 1.3, c + s * 0.3), (c + s * 0.4, c + s * 0.9)], width=w)
        d.line([(c + s * 0.2, c - s * 0.5), (c - s * 0.2, c + s * 1.1)], width=w)
    else:  # orbite
        for k, ang in enumerate((0, 60, 120)):
            box = [c - R, c - R * 0.38, c + R, c + R * 0.38]
            strato = Image.new("L", (L, L), 0)
            ImageDraw.Draw(strato).ellipse(box, outline=255, width=w)
            punti.append(("orbita", strato.rotate(ang, center=(c, c)), None))
        d.ellipse([c - R * 0.14, c - R * 0.14, c + R * 0.14, c + R * 0.14], width=w)
        punti.append((c, c, w * 1.2))


class _Penna:
    """Come ImageDraw, ma disegna sempre in bianco, solo il contorno."""

    def __init__(self, d):
        self.d = d

    def line(self, xy, width=1, joint=None):
        self.d.line(xy, fill=255, width=width, joint=joint)

    def rectangle(self, xy, width=1):
        self.d.rectangle(xy, outline=255, width=width)

    def rounded_rectangle(self, xy, radius=0, width=1):
        self.d.rounded_rectangle(xy, radius=radius, outline=255, width=width)

    def ellipse(self, xy, width=1):
        self.d.ellipse(xy, outline=255, width=width)

    def polygon(self, xy, outline=None):
        pass


def disegna(percorso, arxiv_id, testi, cfg_c):
    lato = cfg_c.get("lato", 1400)
    S = 2                             # doppia risoluzione, poi riduco: bordi lisci
    L = lato * S
    P = {k: _rgb(v) for k, v in cfg_c["colori"].items()}
    rng = random.Random(int(hashlib.sha1(arxiv_id.encode()).hexdigest()[:8], 16))
    motivo = tema(*testi)

    img = _fondo(L, P)
    linee = Image.new("L", (L, L), 0)          # maschera delle linee dell'icona
    d = _Penna(ImageDraw.Draw(linee))   # disegna in bianco sulla maschera delle linee
    w = max(4, L // 180)
    punti = []
    _icona(d, motivo, L, rng, w, punti)
    for p in punti:
        if p[0] == "orbita":
            linee = Image.composite(Image.new("L", (L, L), 255), linee, p[1])
    d = ImageDraw.Draw(linee)
    for p in punti:
        if p[0] != "orbita":
            x, y, r = p
            d.ellipse([x - r, y - r, x + r, y + r], fill=255)

    # bagliore: la stessa maschera sfocata due volte, sotto le linee nitide
    arancio = Image.new("RGB", (L, L), P["linee"])
    for raggio, forza in ((L // 28, 0.9), (L // 90, 1.0)):
        alone = linee.filter(ImageFilter.GaussianBlur(raggio)).point(lambda v: int(v * forza))
        img = Image.composite(arancio, img, alone)
    nucleo = Image.new("RGB", (L, L), P["accento"])
    img = Image.composite(arancio, img, linee)
    img = Image.composite(nucleo, img, linee.filter(ImageFilter.MinFilter(3)).point(lambda v: int(v * 0.5)))

    img = img.resize((lato, lato), Image.LANCZOS)
    img.save(percorso, "JPEG", quality=90, optimize=True)
    return motivo


def salva_da_bytes(percorso, dati, lato):
    """Salva l'immagine del modello come JPEG quadrato del lato voluto."""
    img = Image.open(io.BytesIO(dati)).convert("RGB")
    m = min(img.size)
    img = img.crop(((img.width - m) // 2, (img.height - m) // 2,
                    (img.width + m) // 2, (img.height + m) // 2))
    img.resize((lato, lato), Image.LANCZOS).save(percorso, "JPEG", quality=90, optimize=True)
