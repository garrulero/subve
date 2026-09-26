import unittest
from datetime import date, timedelta
from ai.dates import extract_dates_and_deadlines


class TestDatesExtraction(unittest.TestCase):

    def test_dia_siguiente_pattern(self):
        pub_date = date(2026, 9, 25)
        texto = "El plazo de presentación de solicitudes comenzará el día siguiente al de su publicación en el BOPV."
        f_ap, f_ci, plazo_txt = extract_dates_and_deadlines(texto, pub_date)
        self.assertEqual(f_ap, date(2026, 9, 26))
        self.assertEqual(plazo_txt, "El día siguiente al de la publicación oficial")

    def test_explicit_apertura_pattern(self):
        pub_date = date(2026, 9, 20)
        texto = "Las solicitudes podrán presentarse a partir del 15 de octubre de 2026."
        f_ap, f_ci, plazo_txt = extract_dates_and_deadlines(texto, pub_date)
        self.assertEqual(f_ap, date(2026, 10, 15))

    def test_explicit_cierre_pattern(self):
        pub_date = date(2026, 9, 20)
        texto = "El plazo finalizará el 30 de noviembre de 2026."
        f_ap, f_ci, plazo_txt = extract_dates_and_deadlines(texto, pub_date)
        self.assertEqual(f_ci, date(2026, 11, 30))

    def test_relative_un_mes_pattern(self):
        pub_date = date(2026, 9, 1)
        texto = "El plazo de presentación será de un mes a partir del día siguiente al de la publicación."
        f_ap, f_ci, plazo_txt = extract_dates_and_deadlines(texto, pub_date)
        self.assertEqual(f_ap, date(2026, 9, 2))
        self.assertEqual(f_ci, date(2026, 10, 2))

    def test_none_texto(self):
        pub_date = date(2026, 9, 10)
        f_ap, f_ci, plazo_txt = extract_dates_and_deadlines(None, pub_date)
        self.assertEqual(f_ap, date(2026, 9, 11))
        self.assertIsNone(f_ci)


if __name__ == "__main__":
    unittest.main()
