import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kit.avvisi import Avanzamento

# Questo test usa soltanto la consegna Telegram. Evita di caricare i moduli
# opzionali per PDF e immagini, che non servono a questa unità.
for nome in ("kit.controlli", "kit.copertina", "kit.fonti", "kit.testi"):
    sys.modules.setdefault(nome, types.ModuleType(nome))
from pipeline import consegna


class RipresaTelegramTest(unittest.TestCase):
    def test_pulsante_compare_solo_dopo_i_tentativi_automatici(self):
        avanz = Avanzamento.__new__(Avanzamento)
        avanz.corrente = None
        avanz.stati = {"Voce": ("corso", "")}
        avanz.log = io.StringIO()
        avanz.scrivi = Mock()
        avanz._aggiorna_tg = Mock()
        avanz.manda = Mock(return_value=True)

        env = {"GITHUB_REPOSITORY": "sovietalysrls-ui/ai-paper-in-pillole",
               "GITHUB_RUN_ID": "12345", "MOSTRA_RIPRENDI_TELEGRAM": "1"}
        with patch.dict(os.environ, env, clear=False):
            try:
                raise RuntimeError("prova")
            except RuntimeError as exc:
                avanz.errore("Voce", exc)

        markup = avanz.manda.call_args.kwargs["reply_markup"]
        bottone = markup["inline_keyboard"][0][0]
        self.assertIn("Riprendi", bottone["text"])
        self.assertTrue(bottone["url"].endswith("/actions/workflows/riprendi.yml"))

    def test_la_ripresa_invia_solo_gli_elementi_mancanti(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out, lav = base / "OGGI", base / "OGGI" / ".lavoro"
            (lav / "it").mkdir(parents=True)
            (lav / "it" / "titolo.json").write_text(
                json.dumps({"completo": "Titolo"}), encoding="utf-8")
            (lav / "it" / "descrizione.txt").write_text("Descrizione", encoding="utf-8")

            primo = Mock(tg=True)
            primo.manda.side_effect = [True, False]
            primo.inizia = Mock()
            primo.fatto = Mock()
            with self.assertRaisesRegex(RuntimeError, "1 invii non riusciti"):
                consegna({"telegram": {"manda_file": True}}, ["it"], out, 59, primo, lav)

            secondo = Mock(tg=True)
            secondo.manda.return_value = True
            secondo.inizia = Mock()
            secondo.fatto = Mock()
            consegna({"telegram": {"manda_file": True}}, ["it"], out, 59, secondo, lav)

            secondo.manda.assert_called_once_with("Descrizione")
            self.assertTrue((lav / "consegnato.json").exists())


if __name__ == "__main__":
    unittest.main()
