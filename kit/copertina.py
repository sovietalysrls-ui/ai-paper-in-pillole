"""Passo 8: la copertina della puntata.

Un disegno astratto, sempre negli stessi colori, con un motivo scelto
in base al tema del paper (video, linguaggio, agenti, audio, memoria,
reti...). Nessun testo. La variazione dipende dal numero del paper,
quindi due paper diversi danno due copertine diverse, e lo stesso
paper dà sempre la stessa.

Lo disegna questo programma: niente servizi esterni, niente diritti.
"""
import hashlib
import math
import random
import re

from PIL import Image, ImageDraw, ImageFilter

TEMI = [
    ("onde",   r"audio|voce|voice|speech|parlat|music|sound|suono|ascolt"),
    ("occhio", r"video|immagin|image|vision|visiv|pixel|camera|foto|guard"),
    ("righe",  r"testo|text|linguag|language|parol|llm|token|scritt|lettur|document"),
    ("griglia", r"agent|robot|azion|computer|interfacc|gui|strument|tool|codice|code|program"),
    ("strati", r"memori|ricord|memory|context|contest|storia|cache"),
    ("nodi",   r"rete|grafo|graph|network|connession|relazion|conoscenz|knowledge"),
    ("scala",  r"ragion|reason|matemat|math|logic|calcol|dimostr|step|passi"),
]


def tema(*testi):
    t = " ".join(x for x in testi if x).lower()
    punteggi = [(len(re.findall(rx, t)), nome) for nome, rx in TEMI]
    migliore = max(punteggi)
    return migliore[1] if migliore[0] else "orbite"


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def disegna(percorso, arxiv_id, testi, cfg_c):
    lato = cfg_c.get("lato", 1400)
    S = 2                                   # disegno a doppia risoluzione, poi riduco: bordi lisci
    L = lato * S
    P = {k: _rgb(v) for k, v in cfg_c["colori"].items()}
    rng = random.Random(int(hashlib.sha1(arxiv_id.encode()).hexdigest()[:8], 16))
    motivo = tema(*testi)

    img = Image.new("RGB", (L, L), P["fondo"])
    d = ImageDraw.Draw(img)
    m = int(L * 0.09)                       # margine
    cx, cy = L // 2 + rng.randint(-L // 14, L // 14), L // 2 + rng.randint(-L // 14, L // 14)
    sottile = max(2, L // 400)
    medio = max(4, L // 160)

    # grande forma di fondo, sempre presente: dà riconoscibilità alla serie
    r0 = int(L * rng.uniform(0.30, 0.36))
    d.ellipse([cx - r0, cy - r0, cx + r0, cy + r0], fill=P["principale"])

    if motivo == "onde":
        for k in range(7):
            y0 = m + (L - 2 * m) * (k + 1) / 8
            amp = L * 0.03 * (1 + (k % 3)) * rng.uniform(0.6, 1.2)
            freq = rng.uniform(2, 5)
            fase = rng.uniform(0, math.pi)
            punti = [(x, y0 + amp * math.sin(freq * 2 * math.pi * (x - m) / (L - 2 * m) + fase)
                      * math.sin(math.pi * (x - m) / (L - 2 * m)))
                     for x in range(m, L - m, 8)]
            d.line(punti, fill=P["linee"] if k % 3 else P["sfondo2"], width=medio if k == 3 else sottile)
    elif motivo == "occhio":
        for k in range(9, 0, -1):
            r = r0 * k / 9 * 1.35
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=P["linee"], width=sottile)
        ri = r0 * 0.38
        d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=P["sfondo2"])
        rp = ri * 0.45
        d.ellipse([cx - rp, cy - rp, cx + rp, cy + rp], fill=P["linee"])
    elif motivo == "righe":
        y = m + L * 0.05
        while y < L - m - L * 0.04:
            lung = (L - 2 * m) * rng.uniform(0.35, 1.0)
            x0 = m
            colore = P["linee"] if rng.random() > 0.2 else P["sfondo2"]
            d.line([(x0, y), (x0 + lung, y)], fill=colore, width=medio)
            y += L * 0.045
    elif motivo == "griglia":
        n = 8
        passo = (L - 2 * m) / n
        for i in range(n + 1):
            d.line([(m + i * passo, m), (m + i * passo, L - m)], fill=P["linee"], width=sottile)
            d.line([(m, m + i * passo), (L - m, m + i * passo)], fill=P["linee"], width=sottile)
        x, y = rng.randint(0, 2), rng.randint(0, 2)
        cammino = [(x, y)]
        for _ in range(9):
            if rng.random() < 0.5 and x < n - 1:
                x += 1
            elif y < n - 1:
                y += 1
            cammino.append((x, y))
        pts = [(m + (a + 0.5) * passo, m + (b + 0.5) * passo) for a, b in cammino]
        d.line(pts, fill=P["sfondo2"], width=medio * 2, joint="curve")
        for p in pts:
            d.ellipse([p[0] - medio * 2, p[1] - medio * 2, p[0] + medio * 2, p[1] + medio * 2], fill=P["accento"])
    elif motivo == "strati":
        for k in range(6):
            w = (L - 2 * m) * (0.9 - k * 0.11)
            h = L * 0.07
            x0 = cx - w / 2 + rng.uniform(-L * 0.03, L * 0.03)
            y0 = m + L * 0.12 + k * L * 0.11
            d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h / 2,
                                outline=P["linee"], width=medio, fill=P["sfondo2"] if k == 2 else None)
    elif motivo == "nodi":
        nodi = [(rng.uniform(m, L - m), rng.uniform(m, L - m)) for _ in range(14)]
        for i, a in enumerate(nodi):
            vicini = sorted(nodi, key=lambda b: (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)[1:3]
            for b in vicini:
                d.line([a, b], fill=P["linee"], width=sottile)
        for i, (x, y) in enumerate(nodi):
            r = medio * (3 if i % 4 == 0 else 1.8)
            d.ellipse([x - r, y - r, x + r, y + r], fill=P["sfondo2"] if i % 4 == 0 else P["linee"])
    elif motivo == "scala":
        n = 7
        lato_g = (L - 2 * m) / n
        for i in range(n):
            x0 = m + i * lato_g
            y0 = L - m - (i + 1) * lato_g
            d.rectangle([x0, y0, x0 + lato_g, L - m], outline=P["linee"], width=sottile)
        d.line([(m, L - m), (L - m, m)], fill=P["sfondo2"], width=medio)
    else:  # orbite
        for k in range(5):
            r = min(r0 * (0.6 + k * 0.28), min(cx, cy, L - cx, L - cy) - m * 0.5)
            a0 = rng.uniform(0, 360)
            d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + rng.uniform(120, 300),
                  fill=P["linee"], width=sottile if k % 2 else medio)

    # punto d'accento, piccolo, sempre presente
    ax, ay = rng.uniform(m * 1.5, L - m * 1.5), rng.uniform(m * 1.5, L - m * 1.5)
    ra = L * 0.025
    d.ellipse([ax - ra, ay - ra, ax + ra, ay + ra], fill=P["accento"])

    img = img.resize((lato, lato), Image.LANCZOS)
    # grana leggera, effetto carta
    grana = Image.effect_noise((lato, lato), 18).convert("RGB").filter(ImageFilter.GaussianBlur(0.6))
    img = Image.blend(img, grana, 0.035)
    img.save(percorso, "JPEG", quality=90, optimize=True)
    return motivo
