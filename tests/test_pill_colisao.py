"""Cada pill so cede a vez para uma gravacao nela mesma.

Caso real (dictate.log, 24/09/2026 07:25): o hold parou, um maos-livres comecou
no mesmo segundo e o "pronto" do hold foi descartado pelo guard global. A pill
do hold ficou em "transcrevendo" por 81 minutos.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PyQt5.QtWidgets import QApplication

import dictate


class PillColisaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        dictate._recording, dictate._rec_mode = False, None

    def _pill_ocupada(self, cls, modo_outro):
        pill = cls()
        self.addCleanup(pill.close)
        dictate._recording, dictate._rec_mode = False, None
        pill.show_recording()
        pill.show_busy()
        self.assertEqual(pill.mode, "busy")
        dictate._recording, dictate._rec_mode = True, modo_outro
        return pill

    def test_hold_termina_mesmo_com_maos_livres_gravando(self):
        for secs, esperado in ((1.5, "done"), (-2.0, "fail"), (-3.0, "fail")):
            with self.subTest(secs=secs):
                pill = self._pill_ocupada(dictate.Overlay, "handsfree")
                pill.show_done(secs)
                self.assertEqual(pill.mode, esperado)

    def test_hold_some_em_silencio_com_maos_livres_gravando(self):
        pill = self._pill_ocupada(dictate.Overlay, "handsfree")
        pill.show_done(-1.0)
        self.assertFalse(pill.isVisible())

    def test_maos_livres_termina_mesmo_com_hold_gravando(self):
        pill = self._pill_ocupada(dictate.HandsFreeWindow, "hold")
        pill.show_norm()
        self.assertEqual(pill.mode, "norm")
        pill.show_done(1.5)
        self.assertEqual(pill.mode, "done")

    def test_gravacao_nova_na_mesma_pill_continua_vencendo(self):
        # Decisao da spec #03 item 3, que continua valendo
        for cls, modo in ((dictate.Overlay, "hold"),
                          (dictate.HandsFreeWindow, "handsfree")):
            with self.subTest(pill=cls.__name__):
                pill = self._pill_ocupada(cls, modo)
                pill.show_norm()
                pill.show_done(1.5)
                self.assertEqual(pill.mode, "busy")


if __name__ == "__main__":
    unittest.main()
