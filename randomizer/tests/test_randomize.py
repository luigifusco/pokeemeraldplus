"""Tests for randomizer data transformations."""

from __future__ import annotations

import json
import unittest

from randomizer.randomize import (
    enforce_strong_bosses,
    parse_base_stat_totals,
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


if __name__ == "__main__":
    unittest.main()
