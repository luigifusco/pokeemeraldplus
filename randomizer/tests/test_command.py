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

    def test_per_route_independent_trainers_mode(self) -> None:
        cfg = BuildConfig(
            randomize_wild=True,
            randomize_trainers=True,
            random_mode=RandomMode.PER_ROUTE_INDEPENDENT_TRAINERS,
        )
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--per-route-independent-trainers", args)
        self.assertNotIn("--per-map-consistent", args)
        self.assertNotIn("--per-occurrence", args)

    def test_global_wild_independent_trainers_mode(self) -> None:
        cfg = BuildConfig(
            randomize_wild=True,
            randomize_trainers=True,
            random_mode=RandomMode.GLOBAL_WILD_INDEPENDENT_TRAINERS,
        )
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--global-wild-independent-trainers", args)
        self.assertNotIn("--per-route-independent-trainers", args)
        self.assertNotIn("--per-map-consistent", args)
        self.assertNotIn("--per-occurrence", args)

    def test_stronger_villains_with_restore(self) -> None:
        cfg = BuildConfig(stronger_villains=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--restore", args)
        self.assertIn("--stronger-villains", args)

    def test_stronger_villains_off_by_default(self) -> None:
        args = to_randomize_args(BuildConfig(), python_executable="py")
        self.assertNotIn("--stronger-villains", args)

    def test_stronger_villains_with_trainer_target(self) -> None:
        cfg = BuildConfig(randomize_trainers=True, stronger_villains=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--trainers", args)
        self.assertIn("--stronger-villains", args)
        self.assertNotIn("--restore", args)

    def test_stronger_rival_with_restore(self) -> None:
        cfg = BuildConfig(stronger_rival=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--restore", args)
        self.assertIn("--stronger-rival", args)

    def test_stronger_rival_off_by_default(self) -> None:
        args = to_randomize_args(BuildConfig(), python_executable="py")
        self.assertNotIn("--stronger-rival", args)

    def test_stronger_rival_with_trainer_target(self) -> None:
        cfg = BuildConfig(randomize_trainers=True, stronger_rival=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--trainers", args)
        self.assertIn("--stronger-rival", args)
        self.assertNotIn("--restore", args)

    def test_stronger_wally_with_restore(self) -> None:
        cfg = BuildConfig(stronger_wally=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--restore", args)
        self.assertIn("--stronger-wally", args)

    def test_stronger_wally_off_by_default(self) -> None:
        args = to_randomize_args(BuildConfig(), python_executable="py")
        self.assertNotIn("--stronger-wally", args)

    def test_stronger_wally_with_trainer_target(self) -> None:
        cfg = BuildConfig(randomize_trainers=True, stronger_wally=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--trainers", args)
        self.assertIn("--stronger-wally", args)
        self.assertNotIn("--restore", args)

    def test_stronger_gym_leaders_with_restore(self) -> None:
        cfg = BuildConfig(stronger_gym_leaders=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--restore", args)
        self.assertIn("--stronger-gym-leaders", args)

    def test_stronger_gym_leaders_off_by_default(self) -> None:
        args = to_randomize_args(BuildConfig(), python_executable="py")
        self.assertNotIn("--stronger-gym-leaders", args)

    def test_stronger_gym_leaders_with_trainer_target(self) -> None:
        cfg = BuildConfig(randomize_trainers=True, stronger_gym_leaders=True)
        args = to_randomize_args(cfg, python_executable="py")
        self.assertIn("--trainers", args)
        self.assertIn("--stronger-gym-leaders", args)
        self.assertNotIn("--restore", args)

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
            "FAST_SWIM=0",
            "REPEL_ANY_LEVEL=0",
            "NO_WILD_ENCOUNTERS=0",
            "LEVEL_CAP=0",
            "START_WITH_CAP_CANDY=0",
            "SWAP_TRAINER_POKEMON=0",
            "ADD_TRAINER_POKEMON_IF_SPACE=0",
            "NUZLOCKE_DELETE_FAINTED=0",
            "INSTANT_TEXT=0",
            "FAST_BATTLE_ANIMS=0",
            "FAST_INTRO=0",
            "FORCE_DOUBLE_BATTLES=0",
            "NO_EXP=0",
            "NO_EXP_WILD=0",
            "NO_EXP_TRAINER=0",
            "NO_BATTLE_ITEMS=0",
            "FIRST_SHOP_POKEBALLS=0",
            "REMOVE_POKEMON_CENTER_JOY=0",
            "DISABLE_PCS=0",
            "RANDOM_EVOLUTIONS=0",
            "HARDCODED_RANDOM_EVOLUTIONS=0",
            "OPPONENT_STAT_STAGE_MOD=0",
            "PLAYER_STAT_STAGE_MOD=0",
            "GYM_LEADER_FIRST_ROSTER=0",
            "STARTER_LEVEL=5",
            "WAIT_TIME_DIVISOR=1",
            "EXP_MULTIPLIER=10",
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

    def test_fastest_speed_sets_max_wait_divisor(self) -> None:
        self.assertIn("WAIT_TIME_DIVISOR=1", to_make_args(BuildConfig(fastest_speed=False), jobs=1))
        self.assertIn("WAIT_TIME_DIVISOR=32", to_make_args(BuildConfig(fastest_speed=True), jobs=1))

    def test_fast_battle_anims_is_independent_of_transition_skip(self) -> None:
        args = to_make_args(BuildConfig(fast_battle_anims=True), jobs=1)
        self.assertIn("FAST_BATTLE_ANIMS=1", args)
        self.assertIn("SKIP_BATTLE_TRANSITION=0", args)

    def test_fast_intro_emits_make_flag(self) -> None:
        args = to_make_args(BuildConfig(fast_intro=True), jobs=1)
        self.assertIn("FAST_INTRO=1", args)

    def test_cap_candy_emits_make_flag(self) -> None:
        args = to_make_args(BuildConfig(start_with_cap_candy=True), jobs=1)
        self.assertIn("START_WITH_CAP_CANDY=1", args)

    def test_trainer_pokemon_swap_emits_make_flag(self) -> None:
        args = to_make_args(BuildConfig(swap_trainer_pokemon=True), jobs=1)
        self.assertIn("SWAP_TRAINER_POKEMON=1", args)

    def test_add_trainer_pokemon_if_space_emits_make_flag(self) -> None:
        on = to_make_args(BuildConfig(add_trainer_pokemon_if_space=True), jobs=1)
        self.assertIn("ADD_TRAINER_POKEMON_IF_SPACE=1", on)
        off = to_make_args(BuildConfig(add_trainer_pokemon_if_space=False), jobs=1)
        self.assertIn("ADD_TRAINER_POKEMON_IF_SPACE=0", off)

    def test_exp_multiplier_emits_tenths(self) -> None:
        self.assertIn("EXP_MULTIPLIER=25", to_make_args(BuildConfig(exp_multiplier=2.5), jobs=1))
        # Clamped to the 1.0x..3.0x range (10..30 tenths).
        self.assertIn("EXP_MULTIPLIER=30", to_make_args(BuildConfig(exp_multiplier=5.0), jobs=1))
        self.assertIn("EXP_MULTIPLIER=10", to_make_args(BuildConfig(exp_multiplier=0.5), jobs=1))

    def test_strong_bosses_emits_percentile_when_enabled(self) -> None:
        args = to_randomize_args(
            BuildConfig(guarantee_strong_bosses=True, strong_bosses_percentile=70),
            python_executable="py",
        )
        self.assertIn("--strong-bosses-percentile", args)
        self.assertEqual(args[args.index("--strong-bosses-percentile") + 1], "70")

    def test_strong_bosses_omitted_when_disabled(self) -> None:
        args = to_randomize_args(
            BuildConfig(guarantee_strong_bosses=False, strong_bosses_percentile=70),
            python_executable="py",
        )
        self.assertNotIn("--strong-bosses-percentile", args)

    def test_min_boss_party_size_emitted_when_above_one(self) -> None:
        args = to_randomize_args(BuildConfig(min_boss_party_size=6), python_executable="py")
        self.assertIn("--min-boss-party-size", args)
        self.assertEqual(args[args.index("--min-boss-party-size") + 1], "6")

    def test_min_boss_party_size_omitted_at_one(self) -> None:
        args = to_randomize_args(BuildConfig(min_boss_party_size=1), python_executable="py")
        self.assertNotIn("--min-boss-party-size", args)

    def test_first_shop_pokeballs_emits_make_flag(self) -> None:
        args = to_make_args(BuildConfig(first_shop_pokeballs=True), jobs=1)
        self.assertIn("FIRST_SHOP_POKEBALLS=1", args)

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

    def test_no_exp_wild_and_trainer_toggles(self) -> None:
        self.assertIn("NO_EXP_WILD=1", to_make_args(BuildConfig(no_exp_wild=True), jobs=1))
        self.assertIn("NO_EXP_WILD=0", to_make_args(BuildConfig(no_exp_wild=False), jobs=1))
        self.assertIn("NO_EXP_TRAINER=1", to_make_args(BuildConfig(no_exp_trainer=True), jobs=1))
        self.assertIn("NO_EXP_TRAINER=0", to_make_args(BuildConfig(no_exp_trainer=False), jobs=1))

    def test_no_wild_encounters_toggle(self) -> None:
        self.assertIn(
            "NO_WILD_ENCOUNTERS=1",
            to_make_args(BuildConfig(no_wild_encounters=True), jobs=1),
        )
        self.assertIn(
            "NO_WILD_ENCOUNTERS=0",
            to_make_args(BuildConfig(no_wild_encounters=False), jobs=1),
        )

    def test_no_battle_items_toggle(self) -> None:
        self.assertIn("NO_BATTLE_ITEMS=1", to_make_args(BuildConfig(no_battle_items=True), jobs=1))
        self.assertIn("NO_BATTLE_ITEMS=0", to_make_args(BuildConfig(no_battle_items=False), jobs=1))

    def test_remove_pokemon_center_joy_toggle(self) -> None:
        self.assertIn(
            "REMOVE_POKEMON_CENTER_JOY=1",
            to_make_args(BuildConfig(remove_pokemon_center_joy=True), jobs=1),
        )
        self.assertIn(
            "REMOVE_POKEMON_CENTER_JOY=0",
            to_make_args(BuildConfig(remove_pokemon_center_joy=False), jobs=1),
        )

    def test_disable_pcs_toggle(self) -> None:
        self.assertIn("DISABLE_PCS=1", to_make_args(BuildConfig(disable_pcs=True), jobs=1))
        self.assertIn("DISABLE_PCS=0", to_make_args(BuildConfig(disable_pcs=False), jobs=1))


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
