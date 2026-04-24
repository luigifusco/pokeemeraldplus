"""Qt-native subprocess runner used by the Build & Run tab.

The old Tk GUI spun its own thread on top of ``subprocess.Popen``,
pushed lines into a ``queue.Queue`` and polled it every 50 ms from
the Tk main loop. On Qt we can do better: ``QProcess`` integrates
with the event loop natively, so we can just listen to its
``readyReadStandardOutput``/``readyReadStandardError`` signals.

:class:`CommandRunner` wraps a single ``QProcess`` and emits:

  * ``started(argv)``  -- before the process spawns
  * ``line(text)``      -- for each line of merged stdout/stderr
  * ``finished(code)``  -- on normal or crash exit
  * ``failed(msg)``     -- on spawn errors (e.g. binary not found)

It can only run one command at a time; calling :meth:`run` while busy
raises ``RuntimeError``. For chained commands (randomize -> make ->
follower make) the Build tab daisy-chains these by connecting each
finished signal to the next run call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class CommandRunner(QObject):
    started = Signal(list)    # argv list
    line = Signal(str)        # single line of output, newline-stripped
    finished = Signal(int)    # exit code (QProcess.exitCode())
    failed = Signal(str)      # spawn error text

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._stdout_tail = ""
        self._stderr_tail = ""

    # ----- public API -----

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def run(
        self,
        argv: list[str],
        cwd: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> None:
        if self.is_running():
            raise RuntimeError("CommandRunner is already running a process.")
        if not argv:
            raise ValueError("argv must be non-empty.")

        proc = QProcess(self)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        if cwd is not None:
            proc.setWorkingDirectory(str(cwd))

        env = QProcessEnvironment.systemEnvironment()
        # Keep Python output flushed promptly for a real-time log view.
        env.insert("PYTHONUNBUFFERED", "1")
        if extra_env:
            for k, v in extra_env.items():
                env.insert(k, v)
        proc.setProcessEnvironment(env)

        # Merge stderr into stdout so the log preserves interleaving.
        proc.setProcessChannelMode(QProcess.MergedChannels)

        proc.readyReadStandardOutput.connect(self._on_ready_stdout)
        proc.readyReadStandardError.connect(self._on_ready_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        self._proc = proc
        self._stdout_tail = ""
        self._stderr_tail = ""

        self.started.emit(list(argv))
        proc.start()

    def kill(self) -> None:
        if self._proc is None:
            return
        if self._proc.state() != QProcess.NotRunning:
            self._proc.kill()

    # ----- QProcess slots -----

    def _drain(self, data: bytes, tail_attr: str) -> None:
        text = getattr(self, tail_attr) + data.decode("utf-8", errors="replace")
        *complete, leftover = text.split("\n")
        for ln in complete:
            self.line.emit(ln)
        setattr(self, tail_attr, leftover)

    def _on_ready_stdout(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput())
        if data:
            self._drain(data, "_stdout_tail")

    def _on_ready_stderr(self) -> None:
        # MergedChannels sends everything through stdout; this handler
        # is kept for safety in case the user disables merging later.
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardError())
        if data:
            self._drain(data, "_stderr_tail")

    def _on_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        # Flush any partial tail buffers as a final line.
        for attr in ("_stdout_tail", "_stderr_tail"):
            tail = getattr(self, attr)
            if tail:
                self.line.emit(tail)
                setattr(self, attr, "")
        self._proc = None
        self.finished.emit(code)

    def _on_error(self, err: QProcess.ProcessError) -> None:
        # errorOccurred fires in addition to finished for most cases,
        # but FailedToStart means finished never arrives, so we have
        # to surface it explicitly.
        if err == QProcess.FailedToStart:
            msg = "failed to start process"
            if self._proc is not None:
                msg = self._proc.errorString() or msg
            proc_was = self._proc
            self._proc = None
            self.failed.emit(msg)
            if proc_was is not None:
                proc_was.deleteLater()


def chain(
    runner: CommandRunner,
    steps: Iterable[tuple[list[str], Path | None]],
    on_complete,
) -> None:
    """Sequentially run each (argv, cwd) step on ``runner``.

    Stops at the first non-zero exit code and invokes ``on_complete``
    with that code. ``on_complete(0)`` fires only when every step
    finishes successfully.

    The chain is driven by one-shot signal connections so later steps
    don't fire if the user cancelled and restarted mid-run.
    """

    steps_iter = iter(steps)

    def _next():
        try:
            argv, cwd = next(steps_iter)
        except StopIteration:
            on_complete(0)
            return

        def _handle_finished(code: int) -> None:
            runner.finished.disconnect(_handle_finished)
            runner.failed.disconnect(_handle_failed)
            if code != 0:
                on_complete(code)
            else:
                _next()

        def _handle_failed(_msg: str) -> None:
            runner.finished.disconnect(_handle_finished)
            runner.failed.disconnect(_handle_failed)
            on_complete(-1)

        runner.finished.connect(_handle_finished)
        runner.failed.connect(_handle_failed)
        runner.run(argv, cwd=cwd)

    _next()
