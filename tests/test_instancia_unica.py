import os
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plataforma


class _SocketQueFalha:
    """Socket falso cujo bind levanta o erro dado — simula porta reservada."""

    def __init__(self, erro):
        self._erro = erro
        self.fechado = False

    def bind(self, endereco):
        raise self._erro

    def close(self):
        self.fechado = True


class InstanciaUnicaTest(unittest.TestCase):
    def test_portas_fora_da_faixa_dinamica_do_windows(self):
        for porta in (plataforma.PORTA_DICTATE, plataforma.PORTA_SUPERVISOR,
                      plataforma.PORTA_HISTORICO):
            self.assertLess(porta, 49152)

    def test_pega_o_lock_e_a_segunda_tentativa_ve_ocupada(self):
        livre = socket.socket()
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
        livre.close()

        primeiro, erro = plataforma.travar_instancia_unica(porta)
        self.addCleanup(primeiro.close)
        self.assertIsNone(erro)

        segundo, erro = plataforma.travar_instancia_unica(porta)
        self.assertIsNone(segundo)
        self.assertEqual(erro, "ocupada")

    def test_porta_reservada_pelo_so_nao_vira_instancia_existente(self):
        reservada = OSError(13, "acesso proibido")
        reservada.winerror = 10013
        falso = _SocketQueFalha(reservada)

        with mock.patch("socket.socket", return_value=falso):
            sock, erro = plataforma.travar_instancia_unica(41732)

        self.assertIsNone(sock)
        self.assertNotEqual(erro, "ocupada")
        self.assertIn("10013", erro)
        self.assertTrue(falso.fechado)


if __name__ == "__main__":
    unittest.main()
