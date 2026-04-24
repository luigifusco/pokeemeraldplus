"""FastAPI application for the randomizer web UI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .command import (
    BuildConfig,
    EvoConstraints,
    EvoMode,
    LevelScale,
    RandomMode,
    any_target_selected,
    to_follower_make_args,
    to_make_args,
    to_randomize_args,
)
from .runner import Step, manager


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


class EvoConstraintsModel(BaseModel):
    max_indegree: Optional[int] = None
    max_cycle_length: Optional[int] = None
    min_cycles: Optional[int] = None
    min_cycle_length: Optional[int] = None
    max_avg_indegree: Optional[float] = None

    def to_dc(self) -> EvoConstraints:
        return EvoConstraints(**self.model_dump())


class LevelScaleModel(BaseModel):
    wild_percent: int = 0
    trainer_percent: int = 0

    def to_dc(self) -> LevelScale:
        return LevelScale(**self.model_dump())


class BuildConfigModel(BaseModel):
    # Randomizer
    randomize_wild: bool = False
    randomize_starters: bool = False
    randomize_trainers: bool = False
    random_mode: str = RandomMode.GLOBAL
    level_scale: LevelScaleModel = Field(default_factory=LevelScaleModel)
    # Evolutions
    evo_mode: str = EvoMode.VANILLA
    evo_constraints: EvoConstraintsModel = Field(default_factory=EvoConstraintsModel)
    fast_evolution_anim: bool = False
    # Gameplay
    nuzlocke_delete_fainted: bool = False
    force_doubles: bool = False
    steal_trainer_team: bool = False
    no_exp: bool = False
    negative_exp: bool = False
    no_pokeballs: bool = False
    money_for_moves: bool = False
    start_with_super_rare_candy: bool = False
    walk_through_walls: bool = False
    opponent_stat_stage_mod: int = 0
    player_stat_stage_mod: int = 0
    # Speed
    walk_fast: bool = False
    instant_text: bool = False
    skip_battle_transition: bool = False
    skip_intro_cutscene: bool = False
    skip_fade_anims: bool = False
    fast_stat_anims: bool = False
    manual_battle_text: bool = False
    wait_time_divisor_pow: int = 0
    # Build
    remote_opponent: bool = False

    def to_dc(self) -> BuildConfig:
        data = self.model_dump()
        data["level_scale"] = self.level_scale.to_dc()
        data["evo_constraints"] = self.evo_constraints.to_dc()
        return BuildConfig(**data)


class BuildRequest(BaseModel):
    config: BuildConfigModel
    run_randomize: bool = True
    run_make: bool = True
    build_follower: bool = False
    jobs: Optional[int] = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="pokeemeraldplus randomizer",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    STATIC_DIR.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({"ok": True, "repo": str(REPO_ROOT)})

    @app.post("/api/preview")
    def preview(req: BuildRequest) -> JSONResponse:
        cfg = req.config.to_dc()
        steps: list[dict] = []
        if req.run_randomize and any_target_selected(cfg):
            steps.append({"label": "randomize", "argv": to_randomize_args(cfg)})
        if req.run_make:
            steps.append({"label": "make", "argv": to_make_args(cfg, jobs=req.jobs)})
            if req.build_follower:
                steps.append({"label": "make follower",
                              "argv": to_follower_make_args(cfg, jobs=req.jobs)})
        return JSONResponse({"steps": steps})

    @app.post("/api/build")
    async def build(req: BuildRequest) -> JSONResponse:
        cfg = req.config.to_dc()
        cwd = str(REPO_ROOT)
        steps: list[Step] = []
        if req.run_randomize and any_target_selected(cfg):
            steps.append(Step(argv=to_randomize_args(cfg), cwd=cwd, label="randomize"))
        if req.run_make:
            steps.append(Step(argv=to_make_args(cfg, jobs=req.jobs), cwd=cwd, label="make"))
            if req.build_follower:
                steps.append(Step(argv=to_follower_make_args(cfg, jobs=req.jobs),
                                  cwd=cwd, label="make follower"))
        if not steps:
            raise HTTPException(400, "Nothing to do: no targets selected and run_make is false.")
        run = manager.start(steps)
        return JSONResponse({"run_id": run.run_id, "steps": len(steps)})

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str) -> JSONResponse:
        ok = manager.cancel(run_id)
        if not ok:
            raise HTTPException(404, "run not found")
        return JSONResponse({"ok": True})

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request) -> EventSourceResponse:
        run = manager.get(run_id)
        if run is None:
            raise HTTPException(404, "run not found")

        async def stream():
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(run.queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": event["kind"], "data": json.dumps(event)}
                if event["kind"] == "done":
                    break

        return EventSourceResponse(stream())

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return JSONResponse(
                {
                    "message": (
                        "Web UI scaffold is running. Static shell lands in "
                        "phase 5. GET /api/health to confirm the server works."
                    )
                }
            )
        return FileResponse(index_path)

    return app


app = create_app()
