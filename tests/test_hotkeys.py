import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PyQt5.QtWidgets import QApplication
from pynput.keyboard import Key

import dictate
import plataforma


class _Signal:
    def __init__(self):
        self.calls = 0

    def emit(self):
        self.calls += 1


class HotkeyTest(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.bridge = SimpleNamespace(
            start=_Signal(), stop=_Signal(),
            handsfree_toggle=_Signal(), handsfree_stop=_Signal(),
        )
        self.patches = (
            patch.object(dictate, "bridge", self.bridge, create=True),
            patch.object(dictate, "_pressed", set()),
            patch.object(dictate, "_handsfree_combo_active", False),
            patch.object(dictate, "_hold_combo_active", False),
            patch.object(dictate, "HANDSFREE_HOTKEY",
                         dictate._resolve_hotkey("ctrl_l+alt_l+space")),
            patch.object(dictate, "HOTKEY",
                         dictate._resolve_hotkey("alt_gr/ctrl_r")),
            patch.object(dictate, "log"),
        )
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def test_left_ctrl_does_not_complete_stale_alt_and_space(self):
        dictate._pressed.update((Key.alt_l, Key.space))
        with patch.object(plataforma, "tecla_pressionada", return_value=False):
            dictate.on_press(Key.ctrl_l)
        self.assertEqual(dictate._pressed, {Key.ctrl_l})
        self.assertEqual(self.bridge.handsfree_toggle.calls, 0)

    def test_full_chord_toggles_once_and_right_ctrl_only_starts_hold(self):
        physical = {Key.ctrl_l: True, Key.alt_l: True, Key.space: True}
        with patch.object(plataforma, "tecla_pressionada",
                          side_effect=lambda key: physical.get(key, False)):
            dictate.on_press(Key.ctrl_l)
            dictate.on_press(Key.alt_l)
            self.assertEqual(self.bridge.handsfree_toggle.calls, 0)
            dictate.on_press(Key.space)
            dictate.on_press(Key.space)
        self.assertEqual(self.bridge.handsfree_toggle.calls, 1)
        dictate.on_release(Key.space)
        self.assertFalse(dictate._handsfree_combo_active)
        dictate.on_release(Key.alt_l)
        dictate.on_release(Key.ctrl_l)
        with patch.object(plataforma, "tecla_pressionada", return_value=False):
            dictate.on_press(Key.ctrl_r)
        self.assertEqual(self.bridge.start.calls, 1)
        self.assertEqual(self.bridge.handsfree_toggle.calls, 1)

    def test_stop_button_emits_stop_only(self):
        window = dictate.HandsFreeWindow()
        try:
            window.btn.click()
            self.assertEqual(self.bridge.handsfree_stop.calls, 1)
            self.assertEqual(self.bridge.handsfree_toggle.calls, 0)
        finally:
            window.close()

    def test_windows_checks_left_key_state(self):
        queried = []
        def get_async_key_state(vk):
            queried.append(vk)
            return 0x8000 if vk == 0xA2 else 0
        fake = SimpleNamespace(user32=SimpleNamespace(
            GetAsyncKeyState=get_async_key_state))
        with (
            patch.object(ctypes, "windll", fake, create=True),
            patch.object(plataforma, "IS_WIN", True),
        ):
            self.assertTrue(plataforma.tecla_pressionada(Key.ctrl_l))
            self.assertFalse(plataforma.tecla_pressionada(Key.alt_l))
        self.assertEqual(queried, [0xA2, 0xA4])


if __name__ == "__main__":
    unittest.main()
