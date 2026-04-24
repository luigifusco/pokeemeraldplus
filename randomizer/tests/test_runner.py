"""Smoke tests for randomizer.gui.backend.runner.

Needs PySide6 and a working Qt platform plugin. Runs under
``QT_QPA_PLATFORM=offscreen``.
"""

from __future__ import annotations

import sys
import unittest

try:
    from PySide6.QtCore import QCoreApplication, QTimer
    from randomizer.gui.backend.runner import CommandRunner, chain
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class CommandRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    def _exec_until(self, runner: CommandRunner, timeout_ms: int = 5000):
        lines: list[str] = []
        code: list[int | None] = [None]
        error: list[str | None] = [None]

        runner.line.connect(lines.append)
        runner.finished.connect(lambda c: (code.__setitem__(0, c), self.app.quit()))
        runner.failed.connect(lambda m: (error.__setitem__(0, m), self.app.quit()))

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.app.quit)
        timer.start(timeout_ms)

        self.app.exec()
        return code[0], error[0], lines

    def test_echo_captures_output(self) -> None:
        runner = CommandRunner()
        runner.run(["/bin/sh", "-c", "echo hello; echo world"])
        code, err, lines = self._exec_until(runner)
        self.assertIsNone(err)
        self.assertEqual(code, 0)
        self.assertIn("hello", lines)
        self.assertIn("world", lines)

    def test_nonzero_exit_reported(self) -> None:
        runner = CommandRunner()
        runner.run(["/bin/sh", "-c", "exit 7"])
        code, err, _ = self._exec_until(runner)
        self.assertIsNone(err)
        self.assertEqual(code, 7)

    def test_spawn_failure_emits_failed(self) -> None:
        runner = CommandRunner()
        runner.run(["/definitely/not/a/real/binary/xyz"])
        _code, err, _ = self._exec_until(runner)
        self.assertIsNotNone(err)

    def test_chain_runs_all_on_success(self) -> None:
        runner = CommandRunner()
        completion: list[int | None] = [None]

        def on_done(c: int) -> None:
            completion[0] = c
            self.app.quit()

        lines: list[str] = []
        runner.line.connect(lines.append)

        chain(
            runner,
            [
                (["/bin/sh", "-c", "echo one"], None),
                (["/bin/sh", "-c", "echo two"], None),
                (["/bin/sh", "-c", "echo three"], None),
            ],
            on_done,
        )

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.app.quit)
        timer.start(5000)
        self.app.exec()

        self.assertEqual(completion[0], 0)
        for expected in ("one", "two", "three"):
            self.assertIn(expected, lines)

    def test_chain_stops_on_first_failure(self) -> None:
        runner = CommandRunner()
        completion: list[int | None] = [None]

        def on_done(c: int) -> None:
            completion[0] = c
            self.app.quit()

        lines: list[str] = []
        runner.line.connect(lines.append)

        chain(
            runner,
            [
                (["/bin/sh", "-c", "echo one"], None),
                (["/bin/sh", "-c", "echo two; exit 3"], None),
                (["/bin/sh", "-c", "echo SHOULD_NOT_RUN"], None),
            ],
            on_done,
        )

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(self.app.quit)
        timer.start(5000)
        self.app.exec()

        self.assertEqual(completion[0], 3)
        self.assertIn("one", lines)
        self.assertIn("two", lines)
        self.assertNotIn("SHOULD_NOT_RUN", lines)


if __name__ == "__main__":
    unittest.main()
