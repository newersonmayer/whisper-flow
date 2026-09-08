import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PyQt5.QtWidgets import QApplication

import dictate
import plataforma


class _FakeFunction:
    """Callable simples que aceita os metadados argtypes/restype do ctypes."""

    def __init__(self, implementation):
        self.implementation = implementation
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.implementation(*args)


class OverlayPositioningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_both_pills_use_the_live_work_area_instead_of_stale_qt_geometry(self):
        # Caso real: monitor vertical em x=1920, y=-510, com 1080x1872 úteis.
        # O processo Qt antigo posicionou a pill em y=1462; o rodapé real é 1312.
        live_area = (1920, -510, 1080, 1872)

        with patch.object(
            dictate.plataforma,
            "area_trabalho_do_cursor",
            return_value=live_area,
            create=True,
        ):
            cases = (
                (dictate.Overlay, (2340, 1312)),
                (dictate.HandsFreeWindow, (2299, 1312)),
            )
            for window_type, expected in cases:
                with self.subTest(window=window_type.__name__):
                    window = window_type()
                    try:
                        window.reposition()
                        self.assertEqual((window.x(), window.y()), expected)
                    finally:
                        window.close()

    def test_windows_work_area_comes_from_the_monitor_under_the_cursor(self):
        def get_cursor_pos(point_ref):
            point_ref._obj.x = 2500
            point_ref._obj.y = 100
            return 1

        def monitor_from_point(point, flags):
            return 0xCAFE

        def get_monitor_info(monitor, info_ref):
            rect = info_ref._obj.rcWork
            rect.left = 1920
            rect.top = -510
            rect.right = 3000
            rect.bottom = 1362
            return 1

        fake_user32 = SimpleNamespace(
            GetCursorPos=_FakeFunction(get_cursor_pos),
            MonitorFromPoint=_FakeFunction(monitor_from_point),
            GetMonitorInfoW=_FakeFunction(get_monitor_info),
        )

        with (
            patch.object(ctypes, "windll", SimpleNamespace(user32=fake_user32), create=True),
            patch.object(plataforma, "IS_WIN", True),
        ):
            read_work_area = getattr(plataforma, "area_trabalho_do_cursor", lambda: None)
            self.assertEqual(read_work_area(), (1920, -510, 1080, 1872))


if __name__ == "__main__":
    unittest.main()
