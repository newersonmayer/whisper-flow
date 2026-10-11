"""Ciclo de vida real, isolado de Qt, .env, rede e do hardware de audio."""
import ast
import pathlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "dictate.py"


def load_audio_functions():
    # Executa as funcoes de producao sem os efeitos colaterais dos imports.
    names = {
        "_dispose_stream", "_ensure_stream", "_close_stream", "_stream_keeper",
        "_begin_capture", "_end_capture", "_start_audio", "_confirmar_captura",
        "_no_driver", "_chamada_travada", "_vigia_do_driver",
    }
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    # Estado de partida: o aperto 1 acabou de acontecer e espera o microfone.
    state = dict(
        _stream=None, _stream_lock=threading.Lock(),
        _capture_lock=threading.Lock(), _state_lock=threading.Lock(),
        _capturing=False, _recording=True, _rec_mode="hold",
        _rec_gen=1, _cap_gen=None, _begins_pendentes={1},
        _warm_until=0, MIC_WARM_S=180, SR=16000, BLOCK=1024,
        MIC_CONFIRM_S=3, MIC_NATIVE_TIMEOUT_S=15, EXIT_DRIVER_TRAVADO=75,
        _nativo=None,
        _frames=[], _enc=None, _last_level=0,
        _audio_callback=Mock(), sd=Mock(), log=Mock(),
        time=SimpleNamespace(time=lambda: 1000, perf_counter=lambda: 0,
                             monotonic=lambda: 100),
        os=SimpleNamespace(_exit=Mock(side_effect=SystemExit)),
        warmup_api=Mock(), beep=Mock(), _StreamEncoder=Mock(),
        mute_system=Mock(), unmute_system=Mock(),
        overlay=Mock(), hf_window=Mock(), bridge=Mock(),
    )
    exec(compile(tree, str(SOURCE), "exec"), state)
    return state


class AudioLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.g = load_audio_functions()
        self.sd = self.g["sd"]

    def test_active_stream_is_reused_without_reinitializing(self):
        self.g["_stream"] = Mock(active=True)
        self.assertTrue(self.g["_ensure_stream"]())
        self.sd.InputStream.assert_not_called()
        self.sd._terminate.assert_not_called()

    def test_open_failure_refreshes_before_one_retry(self):
        stream = Mock()
        self.sd.InputStream.side_effect = [RuntimeError("-9986"), stream]
        self.assertTrue(self.g["_ensure_stream"]())
        self.assertEqual([call[0] for call in self.sd.mock_calls],
                         ["InputStream", "_terminate", "_initialize", "InputStream"])
        stream.start.assert_called_once()
        self.assertIs(self.g["_stream"], stream)
        self.assertEqual(self.g["_warm_until"], 1180)

    def test_start_failure_closes_partial_stream_before_refresh(self):
        partial, replacement = Mock(), Mock()
        partial.start.side_effect = RuntimeError("start failed")
        self.sd.InputStream.side_effect = [partial, replacement]
        def terminate():
            partial.close.assert_called_once()
            self.assertTrue(self.g["_stream_lock"].locked())
        self.sd._terminate.side_effect = terminate
        self.assertTrue(self.g["_ensure_stream"]())
        self.assertIs(self.g["_stream"], replacement)

    def test_second_failure_stops_retrying(self):
        self.sd.InputStream.side_effect = RuntimeError("no device")
        self.assertFalse(self.g["_ensure_stream"]())
        self.assertEqual(self.sd.InputStream.call_count, 2)
        self.sd._terminate.assert_called_once()
        self.sd._initialize.assert_called_once()
        self.assertIsNone(self.g["_stream"])

    def test_refresh_failure_returns_without_retrying_open(self):
        for operation in ("_terminate", "_initialize"):
            with self.subTest(operation=operation):
                self.setUp()
                self.sd.InputStream.side_effect = RuntimeError("no device")
                getattr(self.sd, operation).side_effect = RuntimeError("reset failed")
                self.assertFalse(self.g["_ensure_stream"]())
                self.sd.InputStream.assert_called_once()
                getattr(self.sd, operation).assert_called_once()
                if operation == "_terminate":
                    self.sd._initialize.assert_not_called()
                self.assertIsNone(self.g["_stream"])

    def test_close_is_attempted_even_when_stop_fails(self):
        stream = Mock()
        stream.stop.side_effect = RuntimeError("disconnected")
        self.g["_stream"] = stream
        self.g["_close_stream"]()
        stream.close.assert_called_once()
        self.assertIsNone(self.g["_stream"])
        self.g["log"].assert_called()

    def test_dead_stream_is_closed_even_when_stop_fails(self):
        old = Mock(active=False)
        old.stop.side_effect = RuntimeError("disconnected")
        self.g["_stream"] = old
        self.assertTrue(self.g["_ensure_stream"]())
        old.close.assert_called_once()

    def test_idle_close_preserves_active_or_recent_capture(self):
        for capturing, deadline in ((True, 0), (False, 1180)):
            with self.subTest(capturing=capturing, deadline=deadline):
                stream = Mock(active=True)
                self.g.update(_stream=stream, _capturing=capturing,
                              _warm_until=deadline)
                self.g["_close_stream"](only_if_idle=True)
                stream.stop.assert_not_called()
                self.assertIs(self.g["_stream"], stream)

    def test_idle_close_releases_expired_stream(self):
        stream = Mock(active=True)
        self.g["_stream"] = stream
        self.g["_close_stream"](only_if_idle=True)
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        self.assertIsNone(self.g["_stream"])

    def test_keeper_rechecks_idle_state_after_waiting_for_capture(self):
        waiting, release = threading.Event(), threading.Event()
        real_lock = threading.Lock()
        class CaptureGate:
            def __enter__(self):
                if threading.current_thread().name == "keeper-test":
                    waiting.set()
                    if not release.wait(2):
                        raise AssertionError("keeper test timeout")
                real_lock.acquire()
            def __exit__(self, *args):
                real_lock.release()
        self.g["_capture_lock"] = CaptureGate()
        stream = Mock(active=True)
        self.g["_stream"] = stream
        sleeps = iter([None])
        self.g["time"].sleep = lambda _: next(sleeps)
        errors = []
        def keeper():
            try:
                self.g["_stream_keeper"]()
            except StopIteration:
                pass
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=keeper, name="keeper-test", daemon=True)
        thread.start()
        try:
            self.assertTrue(waiting.wait(1))
            self.assertTrue(self.g["_begin_capture"](1))
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        stream.close.assert_not_called()
        self.assertTrue(self.g["_capturing"])
        self.assertIs(self.g["_stream"], stream)

    def test_open_waits_until_stop_and_close_finish(self):
        entered, release, attempted, opened = [threading.Event() for _ in range(4)]
        old = Mock(active=True)
        def stop():
            entered.set()
            if not release.wait(2):
                raise AssertionError("close test timeout")
        old.stop.side_effect = stop
        self.g["_stream"] = old
        def open_stream(**kwargs):
            old.close.assert_called_once()
            opened.set()
            return Mock(active=True)
        self.sd.InputStream.side_effect = open_stream
        errors = []
        def run(fn):
            try:
                fn()
            except BaseException as error:
                errors.append(error)
        def ensure():
            attempted.set()
            self.g["_ensure_stream"]()
        closer = threading.Thread(target=run, args=(self.g["_close_stream"],), daemon=True)
        opener = threading.Thread(target=run, args=(ensure,), daemon=True)
        closer.start()
        try:
            self.assertTrue(entered.wait(1))
            opener.start()
            self.assertTrue(attempted.wait(1))
            self.assertFalse(opened.wait(.1))
        finally:
            release.set()
            closer.join(2)
            if opener.ident is not None:
                opener.join(2)
        self.assertFalse(closer.is_alive() or opener.is_alive())
        self.assertFalse(errors)
        self.assertTrue(opened.is_set())

    def test_releasing_key_during_open_does_not_start_capture(self):
        def open_stream(**kwargs):
            self.g["_recording"] = False
            return Mock(active=True)
        self.sd.InputStream.side_effect = open_stream
        self.assertFalse(self.g["_begin_capture"](1))
        self.assertFalse(self.g["_capturing"])
        self.g["mute_system"].assert_not_called()


class DriverWatchdogTest(unittest.TestCase):
    """Chamada ao PortAudio sem prazo prendia o ditado para sempre (#05)."""

    def setUp(self):
        self.g = load_audio_functions()

    def test_stop_hung_past_deadline_is_reported_with_its_phase(self):
        seen = {}
        stream = Mock()
        def stop():
            seen["no prazo"] = self.g["_chamada_travada"](100 + 15)
            seen["vencida"] = self.g["_chamada_travada"](100 + 16)
        stream.stop.side_effect = stop
        self.g["_stream"] = stream
        self.g["_close_stream"]()
        self.assertIsNone(seen["no prazo"])
        self.assertEqual(seen["vencida"], ("parar microfone", 16))
        # terminou: nao sobra chamada vigiada
        self.assertIsNone(self.g["_chamada_travada"](10_000))

    def test_open_and_portaudio_reset_are_watched(self):
        phases = []
        def open_stream(**kwargs):
            phases.append(self.g["_nativo"][0])
            raise RuntimeError("-9986")
        self.g["sd"].InputStream.side_effect = open_stream
        self.g["sd"]._terminate.side_effect = (
            lambda: phases.append(self.g["_nativo"][0]))
        self.assertFalse(self.g["_ensure_stream"]())
        self.assertEqual(phases, ["abrir microfone", "reiniciar PortAudio",
                                  "abrir microfone"])
        self.assertIsNone(self.g["_nativo"])

    def test_watchdog_restarts_process_when_a_call_overstays(self):
        self.g["_nativo"] = ("parar microfone", 100)
        self.g["time"].monotonic = lambda: 116
        self.g["time"].sleep = lambda _: None
        with self.assertRaises(SystemExit):
            self.g["_vigia_do_driver"]()
        self.g["os"]._exit.assert_called_once_with(75)
        self.assertIn("parar microfone", self.g["log"].call_args[0][0])

    def test_watchdog_stays_quiet_within_deadline(self):
        self.g["_nativo"] = ("abrir microfone", 100)
        self.g["time"].monotonic = lambda: 110
        ticks = iter([None, None])
        self.g["time"].sleep = lambda _: next(ticks)
        with self.assertRaises(StopIteration):
            self.g["_vigia_do_driver"]()
        self.g["os"]._exit.assert_not_called()


class CaptureConfirmationTest(unittest.TestCase):
    """A pill nao pode dizer 'gravando' sem captura por mais de MIC_CONFIRM_S."""

    def setUp(self):
        self.g = load_audio_functions()

    def test_unconfirmed_capture_is_cancelled_and_reported(self):
        self.g["_confirmar_captura"](1, "hold")
        self.assertFalse(self.g["_recording"])
        self.assertIsNone(self.g["_rec_mode"])
        self.g["overlay"].show_done.assert_called_once_with(-4.0)
        self.g["beep"].assert_called_once_with(220, 280)

    def test_handsfree_failure_goes_to_its_own_pill(self):
        self.g["_rec_mode"] = "handsfree"
        self.g["_confirmar_captura"](1, "handsfree")
        self.g["hf_window"].show_done.assert_called_once_with(-4.0)
        self.g["overlay"].show_done.assert_not_called()

    def test_confirmed_capture_is_left_alone(self):
        self.assertTrue(self.g["_begin_capture"](1))
        self.assertNotIn(1, self.g["_begins_pendentes"])
        self.g["_confirmar_captura"](1, "hold")
        self.assertTrue(self.g["_recording"])
        self.assertTrue(self.g["_capturing"])
        self.g["overlay"].show_done.assert_not_called()

    def test_released_key_gets_the_failure_instead_of_the_spinner(self):
        self.g.update(_recording=False, _rec_mode=None)
        self.g["_confirmar_captura"](1, "hold")
        self.g["overlay"].show_done.assert_called_once_with(-4.0)

    def test_newer_dictation_keeps_the_pill(self):
        self.g["_rec_gen"] = 2   # o usuario ja apertou de novo; a pill e do 2
        self.g["_begins_pendentes"].add(2)
        self.g["_confirmar_captura"](1, "hold")
        self.assertTrue(self.g["_recording"])
        self.g["overlay"].show_done.assert_not_called()
        self.g["beep"].assert_not_called()

    def test_late_open_after_cancel_does_not_capture(self):
        self.g["_confirmar_captura"](1, "hold")
        self.assertFalse(self.g["_begin_capture"](1))
        self.assertFalse(self.g["_capturing"])
        self.g["mute_system"].assert_not_called()

    def test_late_open_does_not_capture_for_a_newer_press(self):
        self.g["_rec_gen"] = 2
        self.assertFalse(self.g["_begin_capture"](1))
        self.assertIsNone(self.g["_cap_gen"])
        self.g["mute_system"].assert_not_called()

    def test_stale_stop_does_not_end_a_newer_capture(self):
        self.g["_rec_gen"] = 2
        self.assertTrue(self.g["_begin_capture"](2))
        frames, enc = self.g["_end_capture"](1)
        self.assertEqual((frames, enc), ([], None))
        self.assertTrue(self.g["_capturing"])
        self.g["unmute_system"].assert_not_called()

    def test_own_stop_ends_the_capture(self):
        self.assertTrue(self.g["_begin_capture"](1))
        self.g["_frames"].append("bloco")
        frames, _ = self.g["_end_capture"](1)
        self.assertEqual(frames, ["bloco"])
        self.assertFalse(self.g["_capturing"])
        self.assertIsNone(self.g["_cap_gen"])
        self.g["unmute_system"].assert_called_once()

    def test_open_failing_after_cancel_does_not_hide_the_failure(self):
        self.g["sd"].InputStream.side_effect = RuntimeError("no device")
        self.g["_confirmar_captura"](1, "hold")
        self.g["_start_audio"]("hold", 1)
        self.g["bridge"].abort.emit.assert_not_called()
        self.assertNotIn(1, self.g["_begins_pendentes"])

    def test_open_failing_in_time_aborts_and_skips_confirmation(self):
        self.g["sd"].InputStream.side_effect = RuntimeError("no device")
        self.g["_start_audio"]("hold", 1)
        self.g["bridge"].abort.emit.assert_called_once_with("hold")
        self.g["_confirmar_captura"](1, "hold")
        self.g["overlay"].show_done.assert_not_called()


if __name__ == "__main__":
    unittest.main()
