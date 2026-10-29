import unittest

from kit import voce

LINGUA = {"nome_podcast": "AI Paper in Pillole", "conduttori": {"CARLO": "Carlo", "ARIANNA": "Arianna"}}


def dialogo(n):
    b = [("CARLO", "Gancio."), ("ARIANNA", "Benvenuti ad AI Paper in Pillole. Io sono Arianna."),
         ("CARLO", "E io sono Carlo.")]
    for i in range(n - 3):
        b.append((("ARIANNA", "CARLO")[i % 2], f"Battuta {i}."))
    return b


class DividiTest(unittest.TestCase):
    def test_nessuna_battuta_persa_o_ripetuta(self):
        # Tutte le lunghezze, compreso il caso del 29/10/2026 (46 battute).
        for n in range(4, 120):
            for per_blocco in (6, 10, 14):
                b = dialogo(n)
                apertura, corpo = voce.dividi(b, LINGUA, per_blocco)
                unite = [x for blocco in apertura + corpo for x in blocco]
                self.assertEqual(unite, b, f"{n} battute, blocchi da {per_blocco}")

    def test_controllo_ordine_ferma_i_doppioni(self):
        b = dialogo(10)
        with self.assertRaises(voce.ErroreOrdine):
            voce.controlla_ordine(b, [b[:5], b[3:]])


if __name__ == "__main__":
    unittest.main()
