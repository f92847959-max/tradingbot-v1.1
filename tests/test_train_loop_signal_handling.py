from __future__ import annotations

from scripts.training import process as train_loop


class _DummyProcess:
    def __init__(self) -> None:
        self.terminated = False

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminated = True


def test_sigint_is_deferred_until_second_press(monkeypatch) -> None:
    proc = _DummyProcess()
    monkeypatch.setattr(train_loop, "_active_proc", proc)
    monkeypatch.setattr(train_loop, "_stop_requested", False)
    monkeypatch.setattr(train_loop, "_force_stop_requested", False)

    train_loop._handle_sigint(2, None)

    assert train_loop._stop_requested is True
    assert train_loop._force_stop_requested is False
    assert proc.terminated is False

    train_loop._handle_sigint(2, None)

    assert train_loop._force_stop_requested is True
    assert proc.terminated is True


def test_subprocess_is_isolated_from_console_ctrl_c_on_windows(monkeypatch) -> None:
    monkeypatch.setattr(train_loop.sys, "platform", "win32")
    monkeypatch.setattr(train_loop.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)

    assert train_loop._subprocess_creation_flags() == 512
    assert train_loop._subprocess_start_new_session() is False
