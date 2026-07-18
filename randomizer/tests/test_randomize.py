"""Tests for randomizer data transformations."""

from __future__ import annotations

import json
import random
import unittest
from unittest.mock import patch

from randomizer.randomize import (
    _average_positive_indegree,
    _compute_depths,
    _compute_indegree,
    _find_cycles,
    _pick_constrained_mapping,
    enforce_min_boss_party_size,
    enforce_strong_bosses,
    parse_base_stat_totals,
    randomize_species_in_text,
    randomize_wild_encounters_per_map,
    scale_trainer_party_levels,
    scale_wild_levels_json,
    _percentile,
)


class FixedLevelTest(unittest.TestCase):
    def test_wild_fixed_level_sets_min_and_max(self) -> None:
        text = json.dumps({
            "wild_encounter_groups": [{
                "encounters": [{
                    "land_mons": {
                        "mons": [
                            {"species": "SPECIES_POOCHYENA", "min_level": 2, "max_level": 4},
                            {"species": "SPECIES_ZIGZAGOON", "min_level": 3, "max_level": 5},
                        ]
                    }
                }]
            }]
        })

        data = json.loads(scale_wild_levels_json(text, percent=50, fixed_level=30))
        mons = data["wild_encounter_groups"][0]["encounters"][0]["land_mons"]["mons"]
        self.assertEqual([(m["min_level"], m["max_level"]) for m in mons], [(30, 30), (30, 30)])

    def test_trainer_fixed_level_sets_all_party_levels(self) -> None:
        text = """
static const struct TrainerMonNoItemDefaultMoves sParty[] = {
    {
    .iv = 0,
    .lvl = 5,
    .species = SPECIES_POOCHYENA,
    },
    {
    .iv = 0,
    .lvl = 99,
    .species = SPECIES_ZIGZAGOON,
    },
};
"""

        result = scale_trainer_party_levels(text, percent=-50, fixed_level=42)
        self.assertIn(".lvl = 42", result)
        self.assertNotIn(".lvl = 5", result)
        self.assertNotIn(".lvl = 99", result)


class RouteIndependentTrainersTest(unittest.TestCase):
    def test_global_wild_mapping_is_stable_across_routes(self) -> None:
        text = json.dumps({
            "wild_encounter_groups": [{
                "encounters": [
                    {
                        "map": "MAP_ROUTE101",
                        "land_mons": {"mons": [
                            {"species": "SPECIES_GEODUDE"},
                        ]},
                    },
                    {
                        "map": "MAP_ROUTE112",
                        "land_mons": {"mons": [
                            {"species": "SPECIES_GEODUDE"},
                        ]},
                    },
                ],
            }],
        })

        with patch(
            "randomizer.randomize.random.choice",
            return_value="SPECIES_RALTS",
        ) as choose:
            result = json.loads(
                randomize_species_in_text(
                    text,
                    ["SPECIES_RALTS", "SPECIES_ARON"],
                    per_occurrence=False,
                )
            )

        encounters = result["wild_encounter_groups"][0]["encounters"]
        self.assertEqual(
            encounters[0]["land_mons"]["mons"][0]["species"],
            "SPECIES_RALTS",
        )
        self.assertEqual(
            encounters[1]["land_mons"]["mons"][0]["species"],
            "SPECIES_RALTS",
        )
        choose.assert_called_once()

    def test_wild_species_is_stable_within_route_and_rerolled_across_routes(self) -> None:
        text = json.dumps({
            "wild_encounter_groups": [{
                "encounters": [
                    {
                        "map": "MAP_ROUTE101",
                        "land_mons": {"mons": [
                            {"species": "SPECIES_POOCHYENA"},
                            {"species": "SPECIES_POOCHYENA"},
                        ]},
                    },
                    {
                        "map": "MAP_ROUTE102",
                        "land_mons": {"mons": [
                            {"species": "SPECIES_POOCHYENA"},
                        ]},
                    },
                ],
            }],
        })

        with patch(
            "randomizer.randomize._pick_species",
            side_effect=["SPECIES_RALTS", "SPECIES_ARON"],
        ):
            result = json.loads(
                randomize_wild_encounters_per_map(
                    text,
                    ["SPECIES_RALTS", "SPECIES_ARON"],
                )
            )

        encounters = result["wild_encounter_groups"][0]["encounters"]
        route101 = [mon["species"] for mon in encounters[0]["land_mons"]["mons"]]
        route102 = [mon["species"] for mon in encounters[1]["land_mons"]["mons"]]
        self.assertEqual(route101, ["SPECIES_RALTS", "SPECIES_RALTS"])
        self.assertEqual(route102, ["SPECIES_ARON"])

    def test_trainer_slots_roll_independently(self) -> None:
        text = (
            ".species = SPECIES_POOCHYENA,\n"
            ".species = SPECIES_POOCHYENA,\n"
        )
        with patch(
            "randomizer.randomize.random.choice",
            side_effect=["SPECIES_RALTS", "SPECIES_ARON"],
        ):
            result = randomize_species_in_text(
                text,
                ["SPECIES_RALTS", "SPECIES_ARON"],
                per_occurrence=True,
            )

        self.assertEqual(result.count("SPECIES_RALTS"), 1)
        self.assertEqual(result.count("SPECIES_ARON"), 1)


# Minimal species_info.h fragment: three weak, three strong species.
_FAKE_SPECIES_INFO = """
const struct SpeciesInfo gSpeciesInfo[] =
{
    [SPECIES_NONE] = {0},

    [SPECIES_WEAKA] =
    {
        .baseHP        = 10,
        .baseAttack    = 10,
        .baseDefense   = 10,
        .baseSpeed     = 10,
        .baseSpAttack  = 10,
        .baseSpDefense = 10,
        .types = { TYPE_NORMAL, TYPE_NORMAL },
    },

    [SPECIES_WEAKB] =
    {
        .baseHP        = 20,
        .baseAttack    = 20,
        .baseDefense   = 20,
        .baseSpeed     = 20,
        .baseSpAttack  = 20,
        .baseSpDefense = 20,
        .types = { TYPE_NORMAL, TYPE_NORMAL },
    },

    [SPECIES_MIDC] =
    {
        .baseHP        = 50,
        .baseAttack    = 50,
        .baseDefense   = 50,
        .baseSpeed     = 50,
        .baseSpAttack  = 50,
        .baseSpDefense = 50,
        .types = { TYPE_NORMAL, TYPE_NORMAL },
    },

    [SPECIES_STRONGD] =
    {
        .baseHP        = 100,
        .baseAttack    = 100,
        .baseDefense   = 100,
        .baseSpeed     = 100,
        .baseSpAttack  = 100,
        .baseSpDefense = 100,
        .types = { TYPE_NORMAL, TYPE_NORMAL },
    },
};
"""


class StrongBossesTest(unittest.TestCase):
    def test_parse_base_stat_totals(self) -> None:
        bst = parse_base_stat_totals(_FAKE_SPECIES_INFO)
        self.assertEqual(bst["SPECIES_WEAKA"], 60)
        self.assertEqual(bst["SPECIES_MIDC"], 300)
        self.assertEqual(bst["SPECIES_STRONGD"], 600)
        self.assertNotIn("SPECIES_NONE", bst)

    def test_percentile_endpoints(self) -> None:
        vals = [60, 120, 300, 600]
        self.assertEqual(_percentile(vals, 0), 60)
        self.assertEqual(_percentile(vals, 100), 600)

    def test_boss_team_average_meets_threshold(self) -> None:
        bst = parse_base_stat_totals(_FAKE_SPECIES_INFO)
        pool = ["SPECIES_WEAKA", "SPECIES_WEAKB", "SPECIES_MIDC", "SPECIES_STRONGD"]
        # A boss party rolled entirely weak.
        parties = (
            "static const struct TrainerMonNoItemDefaultMoves sParty_Roxanne1[] = {\n"
            "    {\n    .iv = 0,\n    .lvl = 15,\n    .species = SPECIES_WEAKA,\n    },\n"
            "    {\n    .iv = 0,\n    .lvl = 15,\n    .species = SPECIES_WEAKA,\n    }\n"
            "};\n"
        )
        result = enforce_strong_bosses(parties, pool, bst, 100)
        species = [line.split("= ")[1].rstrip(",")
                   for line in result.splitlines() if ".species" in line]
        avg = sum(bst[s] for s in species) / len(species)
        # 100th percentile threshold is the max BST (600); average must reach it.
        self.assertGreaterEqual(avg, 600)

    def test_non_boss_party_is_untouched(self) -> None:
        bst = parse_base_stat_totals(_FAKE_SPECIES_INFO)
        pool = ["SPECIES_WEAKA", "SPECIES_STRONGD"]
        parties = (
            "static const struct TrainerMonNoItemDefaultMoves sParty_RouteRandomGuy[] = {\n"
            "    {\n    .iv = 0,\n    .lvl = 5,\n    .species = SPECIES_WEAKA,\n    }\n"
            "};\n"
        )
        result = enforce_strong_bosses(parties, pool, bst, 100)
        self.assertEqual(result, parties)


class MinBossPartySizeTest(unittest.TestCase):
    _POOL = ["SPECIES_WEAKA", "SPECIES_WEAKB", "SPECIES_MIDC", "SPECIES_STRONGD"]

    def _boss(self) -> str:
        return (
            "static const struct TrainerMonNoItemDefaultMoves sParty_Roxanne1[] = {\n"
            "    {\n    .iv = 0,\n    .lvl = 15,\n    .species = SPECIES_WEAKA,\n    }\n"
            "};\n"
        )

    def test_pads_boss_to_min_size(self) -> None:
        result = enforce_min_boss_party_size(self._boss(), self._POOL, 6)
        self.assertEqual(result.count(".species ="), 6)
        # Every padded entry keeps the cloned struct fields.
        self.assertEqual(result.count(".lvl = 15"), 6)

    def test_no_op_at_size_one(self) -> None:
        boss = self._boss()
        self.assertEqual(enforce_min_boss_party_size(boss, self._POOL, 1), boss)

    def test_already_large_party_untouched(self) -> None:
        boss = (
            "static const struct TrainerMonNoItemDefaultMoves sParty_Drake[] = {\n"
            "    {\n    .iv = 0,\n    .lvl = 50,\n    .species = SPECIES_MIDC,\n    },\n"
            "    {\n    .iv = 0,\n    .lvl = 50,\n    .species = SPECIES_STRONGD,\n    }\n"
            "};\n"
        )
        self.assertEqual(enforce_min_boss_party_size(boss, self._POOL, 2), boss)

    def test_non_boss_not_padded(self) -> None:
        guy = (
            "static const struct TrainerMonNoItemDefaultMoves sParty_RandomGuy[] = {\n"
            "    {\n    .iv = 0,\n    .lvl = 5,\n    .species = SPECIES_WEAKA,\n    }\n"
            "};\n"
        )
        result = enforce_min_boss_party_size(guy, self._POOL, 6)
        self.assertEqual(result, guy)

    def test_custom_moves_party_pads_with_valid_blocks(self) -> None:
        boss = (
            "static const struct TrainerMonItemCustomMoves sParty_Sidney[] = {\n"
            "    {\n    .iv = 200,\n    .lvl = 49,\n    .species = SPECIES_MIDC,\n"
            "    .heldItem = ITEM_SITRUS_BERRY,\n"
            "    .moves = {MOVE_CRUNCH, MOVE_SWAGGER, MOVE_TAUNT, MOVE_ROAR}\n    }\n"
            "};\n"
        )
        result = enforce_min_boss_party_size(boss, self._POOL, 3)
        self.assertEqual(result.count(".species ="), 3)
        # Cloned mons preserve the held-item/moves structure of the template.
        self.assertEqual(result.count(".heldItem ="), 3)
        self.assertEqual(result.count(".moves ="), 3)


class ConstrainedEvolutionGraphTest(unittest.TestCase):
    def _species(self, count: int) -> list[str]:
        return [f"SPECIES_TEST_{index}" for index in range(count)]

    def _assert_constraints(
        self,
        mapping: dict[str, str],
        *,
        max_indegree: int,
        min_cycle_length: int,
        max_cycle_length: int,
        min_cycles: int,
        max_avg_indegree: float,
        max_tree_depth: int,
    ) -> None:
        self.assertLessEqual(set(mapping.values()), set(mapping))
        self.assertTrue(all(source != target for source, target in mapping.items()))

        indeg = _compute_indegree(mapping)
        cycles = _find_cycles(mapping)
        depths = _compute_depths(mapping, cycles)
        self.assertLessEqual(max(indeg.values()), max_indegree)
        self.assertGreaterEqual(len(cycles), min_cycles)
        self.assertTrue(all(min_cycle_length <= len(cycle) <= max_cycle_length for cycle in cycles))
        self.assertLessEqual(_average_positive_indegree(indeg), max_avg_indegree + 1e-9)
        self.assertLessEqual(max(depths.values()), max_tree_depth)

    def test_cp_sat_constructs_mapping_meeting_all_constraints(self) -> None:
        random.seed(12345)
        species = self._species(25)
        mapping = _pick_constrained_mapping(
            species,
            max_indegree=2,
            max_cycle_length=4,
            min_cycles=3,
            min_cycle_length=4,
            max_avg_indegree=1.25,
            max_tree_depth=2,
        )
        self.assertEqual(set(mapping), set(species))
        self._assert_constraints(
            mapping,
            max_indegree=2,
            min_cycle_length=4,
            max_cycle_length=4,
            min_cycles=3,
            max_avg_indegree=1.25,
            max_tree_depth=2,
        )

    def test_seeded_constrained_mapping_is_deterministic(self) -> None:
        species = self._species(20)
        kwargs = {
            "max_indegree": 3,
            "max_cycle_length": 5,
            "min_cycles": 2,
            "min_cycle_length": 3,
            "max_avg_indegree": 1.5,
            "max_tree_depth": 3,
        }
        random.seed("same-seed")
        first = _pick_constrained_mapping(species, **kwargs)
        random.seed("same-seed")
        second = _pick_constrained_mapping(species, **kwargs)
        self.assertEqual(first, second)

    def test_zero_tree_depth_constructs_only_cycles(self) -> None:
        random.seed(7)
        species = self._species(10)
        mapping = _pick_constrained_mapping(
            species,
            max_indegree=1,
            max_cycle_length=3,
            min_cycles=3,
            min_cycle_length=2,
            max_avg_indegree=1.0,
            max_tree_depth=0,
        )
        self.assertTrue(all(depth == 0 for depth in _compute_depths(mapping).values()))

    def test_impossible_cycle_minimum_fails_immediately(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "require 12 species"):
            _pick_constrained_mapping(
                self._species(10),
                max_indegree=2,
                max_cycle_length=5,
                min_cycles=3,
                min_cycle_length=4,
                max_avg_indegree=None,
                max_tree_depth=2,
            )

    def test_cp_sat_proves_infeasible_degree_and_cycle_combination(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "infeasible"):
            _pick_constrained_mapping(
                self._species(10),
                max_indegree=1,
                max_cycle_length=3,
                min_cycles=1,
                min_cycle_length=3,
                max_avg_indegree=None,
                max_tree_depth=2,
            )


if __name__ == "__main__":
    unittest.main()
