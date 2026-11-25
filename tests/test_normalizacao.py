import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import numpy as np
from PyQt5.QtWidgets import QApplication

import dictate
import historico
import normalizacao


def completion(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class NormalizacaoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whisper-normalizacao-")
        self.addCleanup(self.temp.cleanup)
        log_patch = patch.object(normalizacao, "log")
        log_patch.start()
        self.addCleanup(log_patch.stop)
        self.root = Path(self.temp.name)
        for name in ("SETTINGS_PATH", "PREFS_PATH", "PREFS_EXAMPLE", "VOCAB_PATH",
                     "VOCAB_EXAMPLE", "CORRECOES_PATH"):
            patcher = patch.object(normalizacao, name, str(self.root / name))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.settings(True, 5)
        Path(normalizacao.PREFS_PATH).write_text("- Preserve todas as ideias.", encoding="utf-8")
        Path(normalizacao.VOCAB_PATH).write_text("AGENTS.md global, Codex, VPS", encoding="utf-8")
        Path(normalizacao.CORRECOES_PATH).write_text("agent.global => AGENTS.md global", encoding="utf-8")
        self.client = Mock()
        self.client.with_options.return_value = self.client
        self.client.audio.transcriptions.create.return_value = SimpleNamespace(
            text="ajuste agents.md global e preserve SQL e VPN")
        self.client.chat.completions.create.return_value = completion(
            "Ajuste AGENTS.md global e preserve SQL e VPN.")
        self.report = Mock()

    def settings(self, enabled, minimum):
        Path(normalizacao.SETTINGS_PATH).write_text(json.dumps({
            "normalizar_enabled": enabled, "normalizar_min_seg": minimum,
        }), encoding="utf-8")

    def normalize(self, text="ajuste AGENTS.md global e preserve SQL e VPN", seconds=10):
        return normalizacao.normalizar_texto(
            text, seconds, client=self.client, logger=self.report)

    def test_disabled_short_and_empty_do_not_call_model_or_emit_phase(self):
        for enabled, seconds, text in [(False, 10, "texto"), (True, 4.9, "texto"),
                                       (True, 10, "")]:
            with self.subTest(enabled=enabled, seconds=seconds, text=text):
                self.settings(enabled, 5)
                phase = Mock()
                self.assertEqual(normalizacao.normalizar_texto(
                    text, seconds, client=self.client, on_normalizing=phase), text)
                phase.assert_not_called()
        self.client.chat.completions.create.assert_not_called()

    def test_at_threshold_uses_luna_and_shared_prompt(self):
        phase = Mock()
        with patch.dict(os.environ, {"NORMALIZE_MODEL": "gpt-5.6-luna"}):
            result = normalizacao.normalizar_texto(
                "ajuste AGENTS.md global e preserve SQL e VPN", 5,
                client=self.client, on_normalizing=phase, logger=self.report)
        self.assertEqual(result, "Ajuste AGENTS.md global e preserve SQL e VPN.")
        phase.assert_called_once_with()
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning_effort"], "none")
        self.assertIn("AGENTS.md global, Codex, VPS", request["messages"][0]["content"])

    def test_empty_or_excessively_short_output_preserves_input(self):
        original = "Preserve o pedido completo sobre AGENTS.md global, SQL e VPN."
        for response in ["", None, "ok"]:
            with self.subTest(response=response):
                self.client.chat.completions.create.return_value = completion(response)
                self.assertEqual(self.normalize(original), original)

    def test_model_failure_preserves_input(self):
        self.client.chat.completions.create.side_effect = TimeoutError("simulated timeout")
        self.assertEqual(self.normalize("texto preservado"), "texto preservado")

    def test_personal_preferences_override_example_and_reload(self):
        Path(normalizacao.PREFS_EXAMPLE).write_text("padrao", encoding="utf-8")
        Path(normalizacao.PREFS_PATH).write_text("# comentario\nprimeira", encoding="utf-8")
        self.assertEqual(normalizacao.read_prefs(), "primeira")
        Path(normalizacao.PREFS_PATH).write_text("segunda", encoding="utf-8")
        self.assertEqual(normalizacao.read_prefs(), "segunda")
        Path(normalizacao.PREFS_PATH).unlink()
        self.assertEqual(normalizacao.read_prefs(), "padrao")

    def test_technical_filename_variants_and_ambiguous_terms(self):
        self.assertEqual(normalizacao.corrigir_termos(
            "agents.md global; agents md; agent.global; agents ponto md"),
            "AGENTS.md global; AGENTS.md; AGENTS.md global; AGENTS.md")
        original = "SQL, VPN, VPS, skill, agente global, agents.md_backup e agents.mdx"
        self.assertEqual(normalizacao.corrigir_termos(original), original)

    def test_hotkey_uses_same_normalizer_and_preserves_client_options(self):
        with patch.object(dictate, "client", self.client), patch.object(dictate, "log"):
            self.assertEqual(dictate.normalizar_texto(
                "ajuste AGENTS.md global e preserve SQL e VPN", 10),
                "Ajuste AGENTS.md global e preserve SQL e VPN.")
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], dictate.NORMALIZE_MODEL)
        self.assertEqual(request["timeout"], dictate.NORMALIZE_TIMEOUT_S)

    def test_recording_corrects_terms_before_normalizing(self):
        phase = Mock()
        with patch.object(historico, "get_client", return_value=self.client):
            text, error = historico.transcribe(np.zeros((160000, 1), dtype=np.int16),
                                             on_normalizing=phase)
        self.assertIsNone(error)
        self.assertEqual(text, "Ajuste AGENTS.md global e preserve SQL e VPN.")
        request = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["messages"][1]["content"],
                         "ajuste AGENTS.md global e preserve SQL e VPN")
        phase.assert_called_once_with()
        self.client.audio.transcriptions.create.assert_called_once()

    def test_recording_uses_actual_sample_rate_and_disabled_still_corrects(self):
        for enabled, sr in [(True, 48000), (False, 16000)]:
            with self.subTest(enabled=enabled, sr=sr):
                self.settings(enabled, 5)
                self.client.reset_mock()
                with patch.object(historico, "get_client", return_value=self.client):
                    text, error = historico.transcribe(np.zeros((48000, 1), dtype=np.int16), sr=sr)
                self.assertIsNone(error)
                self.assertEqual(text, "ajuste AGENTS.md global e preserve SQL e VPN")
                self.client.chat.completions.create.assert_not_called()

    def test_normalization_failure_does_not_reupload_recording(self):
        self.client.chat.completions.create.side_effect = TimeoutError("simulated timeout")
        with patch.object(historico, "get_client", return_value=self.client), \
             patch.object(normalizacao, "log"):
            text, error = historico.transcribe(np.zeros((160000, 1), dtype=np.int16))
        self.assertIsNone(error)
        self.assertEqual(text, "ajuste AGENTS.md global e preserve SQL e VPN")
        self.client.audio.transcriptions.create.assert_called_once()


class RecordingPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_recording_worker_emits_phase_and_delivers_normalized_result(self):
        panel = historico.RecordPanel()
        try:
            def transcribe(_audio, on_normalizing):
                on_normalizing()
                self.assertEqual(panel.status.text(), "Organizando o texto…")
                return "Atualize AGENTS.md global.", None
            with patch.object(historico, "transcribe", side_effect=transcribe), \
                 patch.object(historico.pyperclip, "copy") as copy, \
                 patch.object(historico, "save_history") as save:
                panel.btn.setEnabled(False)
                panel._worker(np.zeros((1, 1), dtype=np.int16))
                self.assertEqual(panel.result.toPlainText(), "Atualize AGENTS.md global.")
                copy.assert_called_once_with("Atualize AGENTS.md global.")
                save.assert_called_once_with("Atualize AGENTS.md global.")
                self.assertTrue(panel.btn.isEnabled())
        finally:
            panel.close()

    def test_unexpected_worker_error_reenables_record_button(self):
        panel = historico.RecordPanel()
        try:
            panel.btn.setEnabled(False)
            with patch.object(historico, "transcribe", side_effect=RuntimeError("simulated")):
                panel._worker(np.zeros((1, 1), dtype=np.int16))
            self.assertTrue(panel.btn.isEnabled())
            self.assertIn("simulated", panel.status.text())
        finally:
            panel.close()


if __name__ == "__main__":
    unittest.main()
