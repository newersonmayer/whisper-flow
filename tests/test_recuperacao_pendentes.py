"""Recuperacao de pendentes/ no boot, isolada de Qt, .env, rede e da API."""
import ast
import io
import os
import pathlib
import re
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "dictate.py"
sys.path.insert(0, str(SOURCE.parent))


def load_recovery(pend_dir, sf, transcribe, encode=None):
    names = {"recover_pending", "_quarentenar", "_erro_definitivo"}
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    tree.body = [n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name in names]
    g = dict(
        os=os, re=re, shutil=shutil, glob=__import__("glob"), time=time,
        traceback=__import__("traceback"), datetime=__import__("datetime"),
        PEND_DIR=pend_dir, PEND_QUARENTENA=os.path.join(pend_dir, "quarentena"),
        API_UPLOAD_MAX_BYTES=25 * 1024 * 1024, RECOVER_DELAY_S=60,
        sf=sf, transcribe_bytes=transcribe,
        encode_upload=encode or (lambda data, sr: io.BytesIO(b"x" * 1000)),
        normalizar_texto=lambda t, d: t, save_history=Mock(),
        archive_audio=Mock(side_effect=lambda fp, now: os.remove(fp)),
        log=Mock(),
    )
    exec(compile(tree, str(SOURCE), "exec"), g)
    return g


class RecuperacaoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sf = Mock()
        self.sf.read.return_value = ([0] * 16000, 16000)

    def _wav(self, nome="a.wav"):
        p = os.path.join(self.dir, nome)
        open(p, "wb").close()
        return p

    def _quarentena(self):
        q = os.path.join(self.dir, "quarentena")
        return sorted(os.listdir(q)) if os.path.isdir(q) else []

    def test_400_da_api_vai_para_quarentena_e_nao_volta_no_proximo_boot(self):
        self._wav()
        api = Mock(return_value=("", "Error code: 400 - {'error': {'message': 'Audio file might be corrupted"))
        g = load_recovery(self.dir, self.sf, api)
        g["recover_pending"](delay=0)
        self.assertEqual(self._quarentena(), ["a.wav"])
        api.reset_mock()
        g["recover_pending"](delay=0)
        api.assert_not_called()

    def test_arquivo_acima_de_25_mb_nem_sobe(self):
        self._wav()
        api = Mock()
        g = load_recovery(self.dir, self.sf, api,
                          encode=lambda d, sr: io.BytesIO(b"x" * (26 * 1024 * 1024)))
        g["recover_pending"](delay=0)
        api.assert_not_called()
        self.assertEqual(self._quarentena(), ["a.wav"])

    def test_wav_ilegivel_vai_para_quarentena(self):
        self._wav()
        self.sf.read.side_effect = RuntimeError("Format not recognised")
        g = load_recovery(self.dir, self.sf, Mock())
        g["recover_pending"](delay=0)
        self.assertEqual(self._quarentena(), ["a.wav"])

    def test_falha_de_rede_e_limite_de_taxa_continuam_na_fila(self):
        for err in ("Connection error.", "Request timed out.",
                    "Error code: 429 - rate limit", "Error code: 500 - server"):
            with self.subTest(err=err):
                p = self._wav()
                g = load_recovery(self.dir, self.sf, Mock(return_value=("", err)))
                g["recover_pending"](delay=0)
                self.assertTrue(os.path.exists(p))
                self.assertEqual(self._quarentena(), [])

    def test_sucesso_arquiva_e_salva_no_historico(self):
        p = self._wav()
        g = load_recovery(self.dir, self.sf, Mock(return_value=("oi", None)))
        g["recover_pending"](delay=0)
        g["save_history"].assert_called_once()
        self.assertFalse(os.path.exists(p))
        self.assertEqual(self._quarentena(), [])

    def test_ditado_feito_durante_a_espera_nao_entra_na_recuperacao(self):
        self._wav("velho.wav")
        api = Mock(return_value=("oi", None))
        g = load_recovery(self.dir, self.sf, api)
        # o ditado novo cai em pendentes/ enquanto a recuperacao espera
        g["time"] = Mock(sleep=lambda s: self._wav("novo.wav"))
        g["recover_pending"](delay=60)
        self.assertEqual(api.call_count, 1)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "novo.wav")))

    def test_pasta_vazia_nao_espera(self):
        g = load_recovery(self.dir, self.sf, Mock())
        g["time"] = Mock()
        g["recover_pending"]()
        g["time"].sleep.assert_not_called()


@unittest.skipUnless(os.name == "nt", "so Windows")
class MemoriaMinimaTest(unittest.TestCase):
    def test_piso_duro_fica_registrado_no_processo(self):
        import ctypes
        from ctypes import wintypes
        import plataforma

        msg = plataforma.garantir_memoria_minima(64)
        self.assertEqual(msg, "memoria minima garantida: 64 MB")

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        mn, mx, fl = ctypes.c_size_t(), ctypes.c_size_t(), wintypes.DWORD()
        k32.GetProcessWorkingSetSizeEx.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(wintypes.DWORD)]
        self.assertTrue(k32.GetProcessWorkingSetSizeEx(
            k32.GetCurrentProcess(), ctypes.byref(mn), ctypes.byref(mx), ctypes.byref(fl)))
        self.assertEqual(mn.value, 64 * 1024 * 1024)
        self.assertTrue(fl.value & 0x1, "piso duro (HARDWS_MIN_ENABLE) ausente")

    def test_zero_desliga(self):
        import plataforma
        self.assertIsNone(plataforma.garantir_memoria_minima(0))


if __name__ == "__main__":
    unittest.main()
