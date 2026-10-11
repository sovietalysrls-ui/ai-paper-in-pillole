import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kit.voce import ErroreVoci, controlla_voci


class MotoreFinto:
    def __init__(self):
        self.chiamate = 0

    def blocco(self, turno):
        self.chiamate += 1
        return b"RIFF" + b"0" * 1200


class AvanzamentoFinto:
    def avviso(self, _testo):
        pass

    def inizia(self, _passo, _nota=""):
        pass

    def scrivi(self, _testo):
        pass


class ControlloVociTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.basso_ok = base / "basso_ok.wav"
        self.basso_dubbio = base / "basso_dubbio.wav"
        self.alto_ok = base / "alto_ok.wav"
        for p in (self.basso_ok, self.basso_dubbio, self.alto_ok):
            p.write_bytes(b"RIFF" + b"0" * 1200)
        self.file = [
            ("CARLO", self.basso_ok, [("CARLO", "uno")]),
            ("CARLO", self.basso_dubbio, [("CARLO", "due")]),
            ("ARIANNA", self.alto_ok, [("ARIANNA", "tre")]),
        ]
        self.lingua = {"conduttori": {"CARLO": "Carlo", "ARIANNA": "Arianna"}}
        self.toni = {"CARLO": "basso", "ARIANNA": "alto"}

    def tearDown(self):
        self.tmp.cleanup()

    @patch("kit.audio.durata", return_value=1)
    @patch("kit.audio.tono", side_effect=[100, 230, 240, 225, 110])
    def test_accetta_il_primo_campione_corretto_entro_il_limite(self, _tono, _durata):
        motore = MotoreFinto()
        controlla_voci(motore, self.file, self.toni, self.lingua,
                       AvanzamentoFinto(), "Voce", tentativi=4)
        self.assertEqual(motore.chiamate, 2)

    @patch("kit.audio.durata", return_value=1)
    @patch("kit.audio.tono", side_effect=[100, 230, 240, 230, 230])
    def test_blocca_se_la_voce_resta_errata(self, _tono, _durata):
        motore = MotoreFinto()
        with self.assertRaisesRegex(ErroreVoci, "dopo 2 tentativi"):
            controlla_voci(motore, self.file, self.toni, self.lingua,
                           AvanzamentoFinto(), "Voce", tentativi=2)
        self.assertEqual(motore.chiamate, 2)


if __name__ == "__main__":
    unittest.main()
