"""Tests for randomizer data transformations."""

from __future__ import annotations

import json
import unittest

from randomizer.randomize import scale_trainer_party_levels, scale_wild_levels_json


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


if __name__ == "__main__":
    unittest.main()
