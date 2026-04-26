"""Tests for the FastAPI web UI routes and runner.

We use FastAPI's TestClient for /api/health and /api/preview. The
SSE runner is tested with a tiny fake command (``/bin/sh -c echo``)
inside an event loop so we don't pull in a real build.
"""

from __future__ import annotations

import asyncio
import json
import unittest

from fastapi.testclient import TestClient

from randomizer.webui.app import app
from randomizer.webui.runner import RunManager, Step


class ApiBasics(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertIn("repo", body)

    def test_preview_make_only(self) -> None:
        r = self.client.post(
            "/api/preview",
            json={"config": {}, "run_randomize": True, "run_make": True},
        )
        self.assertEqual(r.status_code, 200, r.text)
        steps = r.json()["steps"]
        # No targets selected -> randomize restores pristine templates before make.
        self.assertEqual([s["label"] for s in steps], ["randomize", "evolution graph", "spoiler report", "make"])
        self.assertIn("--restore", steps[0]["argv"])
        self.assertIn("evolution_graph.py", steps[1]["argv"][1])
        self.assertIn("spoiler_report.py", steps[2]["argv"][1])
        self.assertIn("make", steps[3]["argv"][0])

    def test_preview_with_randomize(self) -> None:
        r = self.client.post(
            "/api/preview",
            json={
                "config": {"randomize_wild": True},
                "run_randomize": True,
                "run_make": False,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        steps = r.json()["steps"]
        self.assertEqual([s["label"] for s in steps], ["randomize", "evolution graph", "spoiler report"])
        self.assertIn("--wild", steps[0]["argv"])

    def test_preview_with_fixed_levels(self) -> None:
        r = self.client.post(
            "/api/preview",
            json={
                "config": {
                    "level_scale": {
                        "wild_fixed_level": 12,
                        "trainer_fixed_level": 34,
                    }
                },
                "run_randomize": True,
                "run_make": False,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        argv = r.json()["steps"][0]["argv"]
        self.assertIn("--restore", argv)
        self.assertEqual(argv[argv.index("--wild-level") + 1], "12")
        self.assertEqual(argv[argv.index("--trainer-level") + 1], "34")

    def test_build_rejects_empty(self) -> None:
        r = self.client.post(
            "/api/build",
            json={"config": {}, "run_randomize": True, "run_make": False},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["steps"], 3)

    def test_stop_unknown_run(self) -> None:
        r = self.client.post("/api/runs/deadbeef/stop")
        self.assertEqual(r.status_code, 404)


class RunnerStream(unittest.IsolatedAsyncioTestCase):
    async def test_echo_chain(self) -> None:
        mgr = RunManager()
        steps = [
            Step(argv=["/bin/sh", "-c", "echo hello; echo world"], label="echo"),
            Step(argv=["/bin/sh", "-c", "echo bye"], label="bye"),
        ]
        run = mgr.start(steps)
        events: list[dict] = []
        while True:
            ev = await asyncio.wait_for(run.queue.get(), timeout=5.0)
            events.append(ev)
            if ev["kind"] == "done":
                break
        await run.task
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds.count("step"), 2)
        self.assertEqual(kinds.count("step_done"), 2)
        lines = [e["text"] for e in events if e["kind"] == "line"]
        self.assertIn("hello", lines)
        self.assertIn("world", lines)
        self.assertIn("bye", lines)
        done = events[-1]
        self.assertEqual(done["exit_code"], 0)
        self.assertFalse(done["cancelled"])

    async def test_failing_step_stops_chain(self) -> None:
        mgr = RunManager()
        steps = [
            Step(argv=["/bin/sh", "-c", "exit 3"], label="fail"),
            Step(argv=["/bin/sh", "-c", "echo never"], label="never"),
        ]
        run = mgr.start(steps)
        events: list[dict] = []
        while True:
            ev = await asyncio.wait_for(run.queue.get(), timeout=5.0)
            events.append(ev)
            if ev["kind"] == "done":
                break
        await run.task
        lines = [e["text"] for e in events if e["kind"] == "line"]
        self.assertNotIn("never", lines)
        self.assertEqual(events[-1]["exit_code"], 3)


if __name__ == "__main__":
    unittest.main()
