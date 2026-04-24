"""Pure command-building layer.

The old Tk GUI inlined randomize.py and make argv construction inside
its button handler (~180 lines of closure). That coupled view state
(Tk variables) with argv serialization, made it impossible to unit
test, and forced every new build flag to thread through a widget.

This module replaces that with:

  * :class:`EvoConstraints`, :class:`LevelScale`, :class:`BuildConfig`
    — plain dataclasses holding all the state the GUI collects.
  * :func:`to_randomize_args` / :func:`to_make_args` /
    :func:`to_follower_make_args` — pure functions mapping a config
    to argv lists.

The Qt tabs populate a :class:`BuildConfig` via ``collect()`` methods
and the Build tab calls the ``to_*_args`` functions; no Qt import
appears in this file so the logic is freely testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import sys


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class RandomMode:
    """How a target's randomization is applied."""

    GLOBAL = "global"          # one species everywhere
    PER_OCCURRENCE = "per-occurrence"
    PER_MAP = "per-map"        # per-map-consistent


class EvoMode:
    """Evolution behavior selected in the Evolutions tab."""

    VANILLA = "vanilla"
    RANDOM = "random"            # RANDOM_EVOLUTIONS=1
    HARDCODED = "hardcoded"      # HARDCODED_RANDOM_EVOLUTIONS=1


@dataclass
class EvoConstraints:
    """Optional constraints fed to ``randomize.py --hardcoded-random-evos``."""

    max_indegree: int | None = None
    max_cycle_length: int | None = None
    min_cycles: int | None = None
    min_cycle_length: int | None = None
    max_avg_indegree: float | None = None


@dataclass
class LevelScale:
    """Level % sliders from the Randomizer tab."""

    wild_percent: int = 0
    trainer_percent: int = 0


@dataclass
class BuildConfig:
    """Complete GUI state consumed by the build pipeline.

    Every field has a default so tests and presets only have to set
    the non-default values. Field names are kebab-free to keep the
    serialization (QSettings / preset JSON) readable.
    """

    # --- Randomizer tab ---
    randomize_wild: bool = False
    randomize_starters: bool = False
    randomize_trainers: bool = False
    random_mode: str = RandomMode.GLOBAL
    level_scale: LevelScale = field(default_factory=LevelScale)

    # --- Evolutions tab ---
    evo_mode: str = EvoMode.VANILLA
    evo_constraints: EvoConstraints = field(default_factory=EvoConstraints)
    fast_evolution_anim: bool = False

    # --- Gameplay tab ---
    nuzlocke_delete_fainted: bool = False
    force_doubles: bool = False
    steal_trainer_team: bool = False
    no_exp: bool = False
    negative_exp: bool = False
    no_pokeballs: bool = False
    money_for_moves: bool = False
    start_with_super_rare_candy: bool = False
    walk_through_walls: bool = False
    opponent_stat_stage_mod: int = 0        # -6..+6
    player_stat_stage_mod: int = 0          # -6..+6

    # --- Speed & Skips tab ---
    walk_fast: bool = False
    instant_text: bool = False
    skip_battle_transition: bool = False
    skip_intro_cutscene: bool = False
    skip_fade_anims: bool = False
    fast_stat_anims: bool = False
    manual_battle_text: bool = False
    wait_time_divisor_pow: int = 0          # 0..5 => divisor = 1..32

    # --- Build & Run tab ---
    remote_opponent: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def any_target_selected(cfg: BuildConfig) -> bool:
    """True when the randomizer should actually shuffle something.

    Used to decide whether to pass ``--restore`` (no shuffling, just
    regenerate the template files) versus specific targets.
    """

    return bool(
        cfg.randomize_wild
        or cfg.randomize_starters
        or cfg.randomize_trainers
    )


# ---------------------------------------------------------------------------
# randomize.py argv
# ---------------------------------------------------------------------------


def to_randomize_args(
    cfg: BuildConfig,
    python_executable: str | None = None,
    script_path: str = "randomizer/randomize.py",
) -> list[str]:
    """Build ``python3 randomizer/randomize.py ...`` argv.

    ``randomize.py`` always runs (even when no targets are selected)
    because it also (a) regenerates the hardcoded evolution header
    when ``evo_mode == HARDCODED`` and (b) applies level scaling on
    top of the restored template files when ``--restore`` is used.
    """

    argv: list[str] = [python_executable or sys.executable, script_path]

    has_targets = any_target_selected(cfg)

    if has_targets:
        if cfg.randomize_wild:
            argv.append("--wild")
        if cfg.randomize_starters:
            argv.append("--starters")
        if cfg.randomize_trainers:
            argv.append("--trainers")
        if cfg.random_mode == RandomMode.PER_OCCURRENCE:
            argv.append("--per-occurrence")
        elif cfg.random_mode == RandomMode.PER_MAP:
            argv.append("--per-map-consistent")
    else:
        # Restore templates; level-scaling block below may still apply
        # modifications on top of the restored files.
        argv.append("--restore")

    ls = cfg.level_scale
    if ls.wild_percent != 0:
        argv.extend(["--wild-level-percent", str(_clamp(ls.wild_percent, -100, 100))])
    if ls.trainer_percent != 0:
        argv.extend(["--trainer-level-percent", str(_clamp(ls.trainer_percent, -100, 100))])

    if cfg.evo_mode == EvoMode.HARDCODED:
        argv.append("--hardcoded-random-evos")
        ec = cfg.evo_constraints
        if ec.max_indegree is not None and ec.max_indegree > 0:
            argv.extend(["--evo-max-indegree", str(ec.max_indegree)])
        if ec.max_cycle_length is not None and ec.max_cycle_length > 0:
            argv.extend(["--evo-max-cycle-length", str(ec.max_cycle_length)])
        if ec.min_cycles is not None and ec.min_cycles > 0:
            argv.extend(["--evo-min-cycles", str(ec.min_cycles)])
        if ec.min_cycle_length is not None and ec.min_cycle_length > 0:
            argv.extend(["--evo-min-cycle-length", str(ec.min_cycle_length)])
        if ec.max_avg_indegree is not None and ec.max_avg_indegree > 0:
            argv.extend(["--evo-max-avg-indegree", str(ec.max_avg_indegree)])

    return argv


# ---------------------------------------------------------------------------
# make argv
# ---------------------------------------------------------------------------


_BOOL_FLAG_FIELDS: tuple[tuple[str, str], ...] = (
    # BuildConfig attribute -> Makefile variable name
    ("fast_evolution_anim", "FAST_EVOLUTION_ANIM"),
    ("walk_fast", "WALK_FAST"),
    ("walk_through_walls", "WALK_THROUGH_WALLS"),
    ("nuzlocke_delete_fainted", "NUZLOCKE_DELETE_FAINTED"),
    ("instant_text", "INSTANT_TEXT"),
    ("skip_battle_transition", "SKIP_BATTLE_TRANSITION"),
    ("skip_intro_cutscene", "SKIP_INTRO_CUTSCENE"),
    ("skip_fade_anims", "SKIP_FADE_ANIMS"),
    ("fast_stat_anims", "FAST_STAT_ANIMS"),
    ("manual_battle_text", "MANUAL_BATTLE_TEXT"),
    ("force_doubles", "FORCE_DOUBLE_BATTLES"),
    ("steal_trainer_team", "STEAL_TRAINER_TEAM"),
    ("no_exp", "NO_EXP"),
    ("negative_exp", "NEGATIVE_EXP"),
    ("no_pokeballs", "NO_POKEBALLS"),
    ("money_for_moves", "MONEY_FOR_MOVES"),
    ("start_with_super_rare_candy", "START_WITH_SUPER_RARE_CANDY"),
)


def _evo_make_flags(cfg: BuildConfig) -> list[str]:
    """RANDOM_EVOLUTIONS / HARDCODED_RANDOM_EVOLUTIONS are mutually
    exclusive in the Qt GUI (single radio group)."""

    return [
        f"RANDOM_EVOLUTIONS={'1' if cfg.evo_mode == EvoMode.RANDOM else '0'}",
        f"HARDCODED_RANDOM_EVOLUTIONS={'1' if cfg.evo_mode == EvoMode.HARDCODED else '0'}",
    ]


def to_make_args(
    cfg: BuildConfig,
    jobs: int | None = None,
) -> list[str]:
    """Build the main ``make`` argv for the primary ROM."""

    jobs = jobs or (os.cpu_count() or 1)
    argv: list[str] = ["make", f"-j{jobs}"]

    for attr, flag in _BOOL_FLAG_FIELDS:
        argv.append(f"{flag}={'1' if getattr(cfg, attr) else '0'}")

    argv.extend(_evo_make_flags(cfg))

    argv.append(f"OPPONENT_STAT_STAGE_MOD={_clamp(cfg.opponent_stat_stage_mod, -6, 6)}")
    argv.append(f"PLAYER_STAT_STAGE_MOD={_clamp(cfg.player_stat_stage_mod, -6, 6)}")

    pow_ = _clamp(cfg.wait_time_divisor_pow, 0, 5)
    argv.append(f"WAIT_TIME_DIVISOR={1 << pow_}")

    if cfg.remote_opponent:
        argv.append("REMOTE_OPPONENT_LEADER=1")

    return argv


def to_follower_make_args(
    cfg: BuildConfig,
    jobs: int | None = None,
) -> list[str] | None:
    """Follower ROM build -- produced only when remote-opponent mode is on.

    The follower is built with a minimal flag set (just
    REMOTE_OPPONENT_FOLLOWER=1); it lives side-by-side with the leader
    ROM so two players can connect without having to rebuild.
    """

    if not cfg.remote_opponent:
        return None

    jobs = jobs or (os.cpu_count() or 1)
    return ["make", f"-j{jobs}", "REMOTE_OPPONENT_FOLLOWER=1"]
