"""Tests for randomizer.webui.command.

Run with: ``python3 -m unittest randomizer.tests.test_command``.

These tests don't import Qt, so they run anywhere Python runs.
"""

from __future__ import annotations

import unittest

from randomizer.webui.command import (
    BuildConfig,
    EvoConstraints,
    EvoMode,
    LevelScale,
    RandomMode,
    to_evolution_graph_args,
    to_make_args,
    to_randomize_args,
    to_spoiler_report_args,
)


class RandomizeArgsTest(unittest.TestCase):
    def test_no_targets_uses_restore(self) -> None:
        cfg = BuildConfig()
        args = to_randomize_args(cfg, python_executable="py")
        self.assertEqual(args, ["py", "randomizer/randomize.py", "--restore"])

    def test_wild_only(self) -> None:
        cfg = BuildConfig(randomize_wild=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertEqual(args, ["py", "randomizer/randomize.py", "--wild"])

    def test_seed_is_passed_before_targets(self) -> None:
        cfg = BuildConfig(seed="abc123", randomize_wild=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertEqual(args[:4], ["py", "randomizer/randomize.py", "--seed", "abc123"])
        self.assertIn("--wild", args)

    def test_all_three_targets_global_mode(self) -> None:
        cfg = BuildConfig(
            randomize_wild=True,
            randomize_starters=True,
            randomize_trainers=True,
        )
        args = to_randomize_args(cfg, python_executable="py")
        self.assertEqual(
            args,
            ["py", "randomizer/randomize.py", "--wild", "--starters", "--trainers"],
        )

    def test_per_occurrence_mode(self) -> None:
        cfg = BuildConfig(randomize_wild=True, random_mode=RandomMode.PER_OCCURRENCE)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--per-occurrence", args)
        self.assertNotIn("--per-map-consistent", args)

    def test_per_map_mode(self) -> None:
        cfg = BuildConfig(randomize_wild=True, random_mode=RandomMode.PER_MAP)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--per-map-consistent", args)
        self.assertNotIn("--per-occurrence", args)

    def test_level_scaling_without_targets(self) -> None:
        cfg = BuildConfig(level_scale=LevelScale(wild_percent=25, trainer_percent=-10))
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--restore", args)
        self.assertEqual(args[args.index("--wild-level-percent") + 1], "25")
        self.assertEqual(args[args.index("--trainer-level-percent") + 1], "-10")

    def test_fixed_levels_without_targets(self) -> None:
        cfg = BuildConfig(level_scale=LevelScale(wild_fixed_level=42, trainer_fixed_level=55))
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--restore", args)
        self.assertEqual(args[args.index("--wild-level") + 1], "42")
        self.assertEqual(args[args.index("--trainer-level") + 1], "55")

    def test_level_scaling_clamped_to_range(self) -> None:
        cfg = BuildConfig(
            level_scale=LevelScale(
                wild_percent=999,
                trainer_percent=-999,
                wild_fixed_level=999,
                trainer_fixed_level=-999,
            )
        )
        args = to_randomize_args(cfg, python_executable="py")
        self.assertEqual(args[args.index("--wild-level-percent") + 1], "100")
        self.assertEqual(args[args.index("--trainer-level-percent") + 1], "-100")
        self.assertEqual(args[args.index("--wild-level") + 1], "100")
        self.assertEqual(args[args.index("--trainer-level") + 1], "1")

    def test_move_randomizer_flags(self) -> None:
        cfg = BuildConfig(
            randomize_level_up_moves=True,
            randomize_egg_moves=True,
            randomize_tm_moves=True,
            randomize_tutor_moves=True,
            randomize_tmhm_compat=True,
            randomize_tutor_compat=True,
            moves_prefer_same_type=True,
            moves_good_damaging_percent=40,
            moves_block_broken=True,
            guaranteed_starting_moves=4,
        )
        args = to_randomize_args(cfg, python_executable="py")
        for flag in (
            "--randomize-level-up-moves",
            "--randomize-egg-moves",
            "--randomize-tm-moves",
            "--randomize-tutor-moves",
            "--randomize-tmhm-compat",
            "--randomize-tutor-compat",
            "--moves-prefer-same-type",
            "--moves-block-broken",
        ):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--moves-good-damaging-percent") + 1], "40")
        self.assertEqual(args[args.index("--guaranteed-starting-moves") + 1], "4")
        self.assertNotIn("--restore", args)

    def test_move_randomizer_numeric_options_are_clamped(self) -> None:
        cfg = BuildConfig(
            randomize_level_up_moves=True,
            moves_good_damaging_percent=999,
            guaranteed_starting_moves=999,
        )
        args = to_randomize_args(cfg, python_executable="py")
        self.assertEqual(args[args.index("--moves-good-damaging-percent") + 1], "100")
        self.assertEqual(args[args.index("--guaranteed-starting-moves") + 1], "4")

    def test_hardcoded_evos_no_constraints(self) -> None:
        cfg = BuildConfig(evo_mode=EvoMode.HARDCODED)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--hardcoded-random-evos", args)
        for flag in (
            "--evo-max-indegree",
            "--evo-max-cycle-length",
            "--evo-min-cycles",
            "--evo-min-cycle-length",
            "--evo-max-avg-indegree",
            "--evo-max-tree-depth",
        ):
            self.assertNotIn(flag, args)

    def test_hardcoded_evos_all_constraints(self) -> None:
        cfg = BuildConfig(
            evo_mode=EvoMode.HARDCODED,
            evo_constraints=EvoConstraints(
                max_indegree=3,
                max_cycle_length=7,
                min_cycles=20,
                min_cycle_length=3,
                max_avg_indegree=1.5,
                max_tree_depth=4,
            ),
        )
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--hardcoded-random-evos", args)
        self.assertEqual(args[args.index("--evo-max-indegree") + 1], "3")
        self.assertEqual(args[args.index("--evo-max-cycle-length") + 1], "7")
        self.assertEqual(args[args.index("--evo-min-cycles") + 1], "20")
        self.assertEqual(args[args.index("--evo-min-cycle-length") + 1], "3")
        self.assertEqual(args[args.index("--evo-max-avg-indegree") + 1], "1.5")
        self.assertEqual(args[args.index("--evo-max-tree-depth") + 1], "4")

    def test_vanilla_and_random_modes_skip_hardcoded_flag(self) -> None:
        for mode in (EvoMode.VANILLA, EvoMode.RANDOM):
            cfg = BuildConfig(
                evo_mode=mode,
                evo_constraints=EvoConstraints(max_indegree=3),
            )
            args = to_randomize_args(cfg, python_executable="py")
            self.assertNotIn("--hardcoded-random-evos", args)
            self.assertNotIn("--evo-max-indegree", args)


class MakeArgsTest(unittest.TestCase):
    def test_defaults_emit_every_bool_flag_as_zero(self) -> None:
        cfg = BuildConfig()
        args = to_make_args(cfg, jobs=4)
        self.assertEqual(args[0], "make")
        self.assertEqual(args[1], "-j4")
        for expected in (
            "FAST_EVOLUTION_ANIM=0",
            "PREVENT_EVOLUTION_CANCEL=0",
            "WALK_FAST=0",
            "NUZLOCKE_DELETE_FAINTED=0",
            "INSTANT_TEXT=0",
            "FAST_BATTLE_ANIMS=0",
            "FORCE_DOUBLE_BATTLES=0",
            "NO_EXP=0",
            "RANDOM_EVOLUTIONS=0",
            "HARDCODED_RANDOM_EVOLUTIONS=0",
            "OPPONENT_STAT_STAGE_MOD=0",
            "PLAYER_STAT_STAGE_MOD=0",
            "GYM_LEADER_FIRST_ROSTER=0",
            "STARTER_LEVEL=5",
            "WAIT_TIME_DIVISOR=1",
        ):
            self.assertIn(expected, args, f"missing {expected} in {args!r}")

    def test_evo_mode_is_mutually_exclusive(self) -> None:
        for mode, expect_random, expect_hardcoded in (
            (EvoMode.VANILLA, "0", "0"),
            (EvoMode.RANDOM, "1", "0"),
            (EvoMode.HARDCODED, "0", "1"),
        ):
            cfg = BuildConfig(evo_mode=mode)
            args = to_make_args(cfg, jobs=1)
            self.assertIn(f"RANDOM_EVOLUTIONS={expect_random}", args)
            self.assertIn(f"HARDCODED_RANDOM_EVOLUTIONS={expect_hardcoded}", args)

    def test_wait_time_divisor_is_power_of_two(self) -> None:
        for pow_, val in ((0, 1), (1, 2), (2, 4), (3, 8), (4, 16), (5, 32), (99, 32)):
            cfg = BuildConfig(wait_time_divisor_pow=pow_)
            args = to_make_args(cfg, jobs=1)
            self.assertIn(f"WAIT_TIME_DIVISOR={val}", args, f"pow={pow_}")

    def test_fast_battle_anims_is_independent_of_transition_skip(self) -> None:
        args = to_make_args(BuildConfig(fast_battle_anims=True), jobs=1)
        self.assertIn("FAST_BATTLE_ANIMS=1", args)
        self.assertIn("SKIP_BATTLE_TRANSITION=0", args)

    def test_stat_stage_clamped(self) -> None:
        cfg = BuildConfig(opponent_stat_stage_mod=999, player_stat_stage_mod=-999)
        args = to_make_args(cfg, jobs=1)
        self.assertIn("OPPONENT_STAT_STAGE_MOD=6", args)
        self.assertIn("PLAYER_STAT_STAGE_MOD=-6", args)

    def test_gym_leader_first_roster_clamped(self) -> None:
        high = to_make_args(BuildConfig(gym_leader_first_roster=99), jobs=1)
        self.assertIn("GYM_LEADER_FIRST_ROSTER=4", high)
        low = to_make_args(BuildConfig(gym_leader_first_roster=-99), jobs=1)
        self.assertIn("GYM_LEADER_FIRST_ROSTER=0", low)

    def test_starter_level_clamped(self) -> None:
        high = to_make_args(BuildConfig(level_scale=LevelScale(starter_level=999)), jobs=1)
        self.assertIn("STARTER_LEVEL=100", high)
        low = to_make_args(BuildConfig(level_scale=LevelScale(starter_level=-999)), jobs=1)
        self.assertIn("STARTER_LEVEL=1", low)

    def test_webui_opponent_toggle(self) -> None:
        on = to_make_args(BuildConfig(webui_opponent=True), jobs=1)
        self.assertIn("WEBUI_OPPONENT=1", on)
        off = to_make_args(BuildConfig(webui_opponent=False), jobs=1)
        self.assertIn("WEBUI_OPPONENT=0", off)

    def test_evolution_cancel_toggle(self) -> None:
        on = to_make_args(BuildConfig(prevent_evolution_cancel=True), jobs=1)
        self.assertIn("PREVENT_EVOLUTION_CANCEL=1", on)
        off = to_make_args(BuildConfig(prevent_evolution_cancel=False), jobs=1)
        self.assertIn("PREVENT_EVOLUTION_CANCEL=0", off)


class ReportArgsTest(unittest.TestCase):
    def test_report_steps_use_python(self) -> None:
        self.assertEqual(
            to_evolution_graph_args(python_executable="py"),
            ["py", "randomizer/evolution_graph.py"],
        )
        self.assertEqual(
            to_spoiler_report_args(python_executable="py"),
            ["py", "randomizer/spoiler_report.py"],
        )


if __name__ == "__main__":
    unittest.main()
