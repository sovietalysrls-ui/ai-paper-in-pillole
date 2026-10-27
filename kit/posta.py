"""Mail di emergenza: l'articolo pronto da caricare a mano.

Si usa quando il sito non accetta l'articolo nemmeno al terzo tentativo
(il server di Tophost blocca alcuni server di GitHub).

La mail contiene:
- nel testo: titolo, estratto, categoria, tag e l'articolo già impaginato
  (titoletti, grassetti, elenchi), con la copertina in alto;
- in allegato: la copertina (copertina.jpg) e l'articolo in HTML
  (articolo.html), da incollare nell'"Editor di codice" di WordPress.

La mail parte con SMTP, il sistema con cui i programmi spediscono la posta.
Servono due segreti di GitHub:
  MAIL_UTENTE     l'indirizzo che spedisce (per esempio un indirizzo Gmail)
  MAIL_PASSWORD   la sua "password per le app" (non la password normale)
Facoltativo:
  MAIL_SERVER     server e porta, se non è Gmail (esempio: smtp.libero.it:465)
Il destinatario sta in config.yaml, voce posta > destinatario.
"""
import html as _html
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path


class ErrorePosta(RuntimeError):
    pass


def _server():
    s = os.environ.get("MAIL_SERVER", "").strip() or "smtp.gmail.com:465"
    host, _, porta = s.partition(":")
    return host, int(porta or 465)


def _solo_testo(html):
    """L'articolo come testo semplice, per i programmi di posta senza HTML."""
    t = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n== \1 ==\n", html, flags=re.S)
    t = re.sub(r"<li[^>]*>", "\n- ", t)
    t = re.sub(r"</p>|<br\s*/?>", "\n\n", t)
    t = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"\2 (\1)", t, flags=re.S)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def componi(cartella, meta, html_articolo, destinatario, mittente):
    """Prepara la mail (senza spedirla). Restituisce un EmailMessage."""
    d = Path(cartella)
    titolo = meta["titolo"]
    tag = ", ".join(meta.get("tag", []))
    categoria = meta.get("categoria", "")
    copertina = d / "copertina.jpg"

    m = EmailMessage()
    m["Subject"] = f"Da caricare a mano: {titolo}"
    m["From"] = mittente
    m["To"] = destinatario

    testo = (f"Il sito non ha accettato l'articolo dopo 3 tentativi.\n"
             f"Qui sotto c'è tutto per caricarlo a mano.\n\n"
             f"TITOLO\n{titolo}\n\nESTRATTO\n{meta.get('estratto', '')}\n\n"
             f"CATEGORIA\n{categoria}\n\nTAG\n{tag}\n\n"
             f"IMMAGINE IN EVIDENZA\nnell'allegato copertina.jpg\n\n"
             f"ARTICOLO\n\n{_solo_testo(html_articolo)}\n")
    m.set_content(testo)

    cid = make_msgid(domain="aipaper.local")
    e = _html.escape
    img = (f'<p><img src="cid:{cid[1:-1]}" alt="{e(titolo)}" '
           f'style="max-width:100%;height:auto;border-radius:6px"></p>') if copertina.exists() else ""
    scheda = (
        '<table style="border-collapse:collapse;font-size:14px;margin:12px 0">'
        f'<tr><td style="padding:4px 12px 4px 0;color:#666">Titolo</td><td><b>{e(titolo)}</b></td></tr>'
        f'<tr><td style="padding:4px 12px 4px 0;color:#666">Estratto</td><td>{e(meta.get("estratto", ""))}</td></tr>'
        f'<tr><td style="padding:4px 12px 4px 0;color:#666">Categoria</td><td>{e(categoria)}</td></tr>'
        f'<tr><td style="padding:4px 12px 4px 0;color:#666">Tag</td><td>{e(tag)}</td></tr>'
        '</table>')
    corpo = f"""<!doctype html><html><body style="font-family:Georgia,serif;max-width:720px;margin:auto;line-height:1.55;color:#222">
<div style="background:#fff4d6;border:1px solid #e6c46a;padding:12px 14px;border-radius:6px;font-family:Arial,sans-serif;font-size:14px">
<b>Il sito non ha accettato l'articolo dopo 3 tentativi.</b><br>
Come caricarlo a mano: in WordPress crea un nuovo articolo, copia il titolo,
poi seleziona tutto il testo sotto la riga grigia e incollalo.
In alternativa apri l'allegato <b>articolo.html</b> e incollalo nell'Editor di codice.
L'immagine in evidenza è l'allegato <b>copertina.jpg</b>.
</div>
<h1 style="font-size:26px">{e(titolo)}</h1>
{img}
{scheda}
<hr style="border:0;border-top:2px solid #ccc;margin:18px 0">
{html_articolo}
</body></html>"""
    m.add_alternative(corpo, subtype="html")
    if copertina.exists():
        m.get_payload()[1].add_related(copertina.read_bytes(), "image", "jpeg", cid=cid)
        m.add_attachment(copertina.read_bytes(), maintype="image", subtype="jpeg", filename="copertina.jpg")
    m.add_attachment(html_articolo.encode("utf-8"), maintype="text", subtype="html", filename="articolo.html")
    return m


def manda_articolo(cartella, meta, html_articolo, destinatario):
    """Spedisce la mail. Solleva ErrorePosta se non è possibile."""
    utente = os.environ.get("MAIL_UTENTE", "").strip()
    password = os.environ.get("MAIL_PASSWORD", "").replace(" ", "").strip()
    if not utente or not password:
        raise ErrorePosta("mancano i segreti MAIL_UTENTE e MAIL_PASSWORD")
    if not destinatario:
        raise ErrorePosta("manca posta > destinatario in config.yaml")
    m = componi(cartella, meta, html_articolo, destinatario, utente)
    host, porta = _server()
    # Prima la porta indicata, poi l'altra porta standard: alcuni server
    # chiudono la connessione su una delle due.
    porte = [porta] + [q for q in (465, 587) if q != porta]
    errori = []
    for q in porte:
        fase = "connessione"
        try:
            if q == 465:
                s = smtplib.SMTP_SSL(host, q, context=ssl.create_default_context(), timeout=60)
            else:
                s = smtplib.SMTP(host, q, timeout=60)
                s.ehlo()
                fase = "cifratura"
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            with s:
                fase = "accesso"
                s.login(utente, password)
                fase = "invio"
                s.send_message(m)
            return q
        except smtplib.SMTPAuthenticationError as e:
            raise ErrorePosta(f"{host}: utente o password per le app rifiutati ({e.smtp_code})") from e
        except (smtplib.SMTPException, OSError) as e:
            errori.append(f"porta {q}, fase {fase}: {e}")
    # Indizi per capire il problema, senza mostrare i segreti.
    dominio = utente.split("@")[-1] if "@" in utente else "(indirizzo senza @)"
    indizi = (f"mittente @{dominio}, password di {len(password)} caratteri"
              + ("" if password.isalpha() and password.isascii() else ", con caratteri non lettere"))
    raise ErrorePosta(f"{host}: " + " | ".join(errori) + f" [{indizi}]")
