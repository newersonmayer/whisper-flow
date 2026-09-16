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
        "_begin_capture", "_end_capture",
    }
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    state = dict(
        _stream=None, _stream_lock=threading.Lock(),
        _capture_lock=threading.Lock(), _capturing=False, _recording=True,
        _warm_until=0, MIC_WARM_S=180, SR=16000, BLOCK=1024,
        _frames=[], _enc=None, _last_level=0,
        _audio_callback=Mock(), sd=Mock(), log=Mock(),
        time=SimpleNamespace(time=lambda: 1000, perf_counter=lambda: 0),
        warmup_api=Mock(), beep=Mock(), _StreamEncoder=Mock(),
        mute_system=Mock(), unmute_system=Mock(),
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
            self.assertTrue(self.g["_begin_capture"]())
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
        self.assertFalse(self.g["_begin_capture"]())
        self.assertFalse(self.g["_capturing"])
        self.g["mute_system"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
