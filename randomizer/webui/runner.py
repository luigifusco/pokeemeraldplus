"""Async subprocess runner with per-run line queues.

The web UI needs to:

1. Kick off a build (sequence of subprocess invocations).
2. Stream the combined stdout/stderr to a browser tab in real time.
3. Let the user cancel.

``Run`` encapsulates a single sequential chain of commands.
``RunManager`` keeps a dict of runs keyed by ``run_id``.
"""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence


@dataclass
class Step:
    argv: Sequence[str]
    cwd: Optional[str] = None
    label: Optional[str] = None


@dataclass
class Run:
    run_id: str
    steps: list[Step]
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None
    process: Optional[asyncio.subprocess.Process] = None
    cancelled: bool = False
    exit_code: Optional[int] = None
    done: bool = False

    async def _emit(self, kind: str, **payload) -> None:
        await self.queue.put({"kind": kind, **payload})

    async def run(self) -> None:
        try:
            for index, step in enumerate(self.steps):
                if self.cancelled:
                    break
                await self._emit(
                    "step",
                    index=index,
                    total=len(self.steps),
                    label=step.label or step.argv[0],
                    argv=list(step.argv),
                )
                code = await self._run_step(step)
                await self._emit("step_done", index=index, exit_code=code)
                if code != 0:
                    self.exit_code = code
                    await self._emit("error", message=f"step {index} exited {code}")
                    break
            else:
                self.exit_code = 0
            if self.exit_code is None:
                # Cancelled before first step finished.
                self.exit_code = 130 if self.cancelled else -1
        except Exception as exc:  # pragma: no cover - defensive
            await self._emit("error", message=f"runner crashed: {exc!r}")
            self.exit_code = -1
        finally:
            self.done = True
            await self._emit("done", exit_code=self.exit_code, cancelled=self.cancelled)

    async def _run_step(self, step: Step) -> int:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = await asyncio.create_subprocess_exec(
                *step.argv,
                cwd=step.cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            await self._emit("line", text=f"[error] {exc}")
            return 127
        self.process = proc

        assert proc.stdout is not None
        while True:
            try:
                chunk = await proc.stdout.readline()
            except asyncio.CancelledError:
                raise
            if not chunk:
                break
            try:
                text = chunk.decode("utf-8", errors="replace").rstrip("\n")
            except Exception:
                text = repr(chunk)
            await self._emit("line", text=text)

        code = await proc.wait()
        self.process = None
        return code

    def request_cancel(self) -> None:
        self.cancelled = True
        proc = self.process
        if proc and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def start(self, steps: Iterable[Step]) -> Run:
        run_id = uuid.uuid4().hex[:12]
        run = Run(run_id=run_id, steps=list(steps))
        self._runs[run_id] = run
        run.task = asyncio.create_task(run.run())
        return run

    def get(self, run_id: str) -> Optional[Run]:
        return self._runs.get(run_id)

    def cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if not run:
            return False
        run.request_cancel()
        return True

    def forget(self, run_id: str) -> None:
        self._runs.pop(run_id, None)


manager = RunManager()
