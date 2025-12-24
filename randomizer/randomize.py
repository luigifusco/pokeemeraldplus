import argparse
import json
import random
import re
from pathlib import Path


RANDOMIZE_SPECIES_PATTERN = re.compile(r"\bSPECIES_[A-Z0-9_]+\b")
MOVES_FIELD_PATTERN = re.compile(r"(?m)^\s*\.moves\s*=\s*\{[^}]*\}\s*,?\s*$\n?")
TRAINER_LVL_PATTERN = re.compile(r"(?m)(^\s*\.lvl\s*=\s*)(\d+)(\s*,)")


def _clamp_level(level: int) -> int:
    return max(1, min(100, level))


def _scale_level(level: int, percent: int) -> int:
    factor = 1.0 + (percent / 100.0)
    return _clamp_level(int(round(level * factor)))


def scale_wild_levels_json(text: str, percent: int) -> str:
    if percent == 0:
        return text

    data = json.loads(text)
    for group in data.get("wild_encounter_groups", []):
        for encounter in group.get("encounters", []):
            for field_name, field_value in list(encounter.items()):
                if not isinstance(field_value, dict):
                    continue
                mons = field_value.get("mons")
                if not isinstance(mons, list):
                    continue
                for mon in mons:
                    if not isinstance(mon, dict):
                        continue
                    if "min_level" in mon and isinstance(mon["min_level"], int):
                        mon["min_level"] = _scale_level(mon["min_level"], percent)
                    if "max_level" in mon and isinstance(mon["max_level"], int):
                        mon["max_level"] = _scale_level(mon["max_level"], percent)
                    if (
                        "min_level" in mon
                        and "max_level" in mon
                        and isinstance(mon["min_level"], int)
                        and isinstance(mon["max_level"], int)
                        and mon["min_level"] > mon["max_level"]
                    ):
                        mon["min_level"], mon["max_level"] = mon["max_level"], mon["min_level"]

    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def scale_trainer_party_levels(text: str, percent: int) -> str:
    if percent == 0:
        return text

    def repl(match: re.Match[str]) -> str:
        prefix, lvl_str, suffix = match.groups()
        new_lvl = _scale_level(int(lvl_str), percent)
        return f"{prefix}{new_lvl}{suffix}"

    return TRAINER_LVL_PATTERN.sub(repl, text)


def convert_custom_moves_trainer_parties_to_default_moves(text: str) -> str:
    text = text.replace(
        "struct TrainerMonNoItemCustomMoves", "struct TrainerMonNoItemDefaultMoves"
    )
    text = text.replace(
        "struct TrainerMonItemCustomMoves", "struct TrainerMonItemDefaultMoves"
    )
    text = MOVES_FIELD_PATTERN.sub("", text)
    return text


def convert_trainers_to_default_moves(text: str) -> str:
    text = text.replace("NO_ITEM_CUSTOM_MOVES(", "NO_ITEM_DEFAULT_MOVES(")
    text = text.replace("ITEM_CUSTOM_MOVES(", "ITEM_DEFAULT_MOVES(")
    return text


def randomize_species_in_text(text: str, all_species: list[str], *, per_occurrence: bool) -> str:
    mapping: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in ("SPECIES_NONE", "SPECIES_EGG"):
            return token
        if per_occurrence:
            choice = random.choice(all_species)
            if choice == token and len(all_species) > 1:
                while choice == token:
                    choice = random.choice(all_species)
            return choice

        if token not in mapping:
            choice = random.choice(all_species)
            if choice == token and len(all_species) > 1:
                while choice == token:
                    choice = random.choice(all_species)
            mapping[token] = choice
        return mapping[token]

    return RANDOMIZE_SPECIES_PATTERN.sub(repl, text)


def _pick_species(all_species: list[str], *, avoid: str | None = None) -> str:
    choice = random.choice(all_species)
    if avoid is not None and choice == avoid and len(all_species) > 1:
        while choice == avoid:
            choice = random.choice(all_species)
    return choice


def randomize_wild_encounters_per_map(text: str, all_species: list[str]) -> str:
    data = json.loads(text)

    def replace_in_obj(obj, mapping: dict[str, str]):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if isinstance(v, str) and RANDOMIZE_SPECIES_PATTERN.fullmatch(v):
                    if v in ("SPECIES_NONE", "SPECIES_EGG"):
                        continue
                    if v not in mapping:
                        mapping[v] = _pick_species(all_species, avoid=v)
                    obj[k] = mapping[v]
                else:
                    replace_in_obj(v, mapping)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                if isinstance(v, str) and RANDOMIZE_SPECIES_PATTERN.fullmatch(v):
                    if v in ("SPECIES_NONE", "SPECIES_EGG"):
                        continue
                    if v not in mapping:
                        mapping[v] = _pick_species(all_species, avoid=v)
                    obj[i] = mapping[v]
                else:
                    replace_in_obj(v, mapping)

    for group in data.get("wild_encounter_groups", []):
        for encounter in group.get("encounters", []):
            mapping: dict[str, str] = {}
            replace_in_obj(encounter, mapping)

    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def restore_originals(randomizer_dir: Path, repo_root: Path) -> None:
    targets = (
        "src/data/wild_encounters.json",
        "src/starter_choose.c",
        "src/data/trainer_parties.h",
        "src/data/trainers.h",
    )

    # Restore from templates in randomizer/.
    template_map = {
        "src/data/wild_encounters.json": randomizer_dir / "wild_encounters.json",
        "src/starter_choose.c": randomizer_dir / "starter_choose.c",
        "src/data/trainer_parties.h": randomizer_dir / "trainer_parties.h",
        "src/data/trainers.h": randomizer_dir / "trainers.h",
    }

    for rel in targets:
        src = template_map.get(rel)
        if src is None or not src.exists():
            raise FileNotFoundError(f"No template available to restore {rel}: {src}")
        dst = repo_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Randomize species in selected pokeemerald source/data files using templates in randomizer/."
    )
    parser.add_argument(
        "--wild",
        action="store_true",
        help="Randomize wild encounters (src/data/wild_encounters.json).",
    )
    parser.add_argument(
        "--starters",
        action="store_true",
        help="Randomize starters (src/starter_choose.c).",
    )
    parser.add_argument(
        "--trainers",
        action="store_true",
        help=(
            "Randomize trainer parties (src/data/trainer_parties.h) and update trainers "
            "(src/data/trainers.h). Also converts custom-move parties to default-moves."
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Randomize wilds, starters, and trainers (default if no flags are given).",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Restore original (unrandomized) files from randomizer/ templates.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--per-occurrence",
        action="store_true",
        help="Replace each SPECIES_* occurrence independently (no stable mapping).",
    )
    mode.add_argument(
        "--per-map-consistent",
        action="store_true",
        help="For wild encounters, keep replacements consistent within each map.",
    )

    parser.add_argument(
        "--level-percent",
        type=int,
        default=0,
        help=(
            "Scale wild encounter and trainer party levels by a percentage. "
            "Example: 25 increases levels by 25%%, -20 decreases by 20%%. "
            "Levels are clamped to 1..100."
        ),
    )

    parser.add_argument(
        "--wild-level-percent",
        type=int,
        default=None,
        help=(
            "Scale wild encounter levels (min_level/max_level) by a percentage. "
            "Example: 25 increases levels by 25%%, -20 decreases by 20%%. "
            "Levels are clamped to 1..100."
        ),
    )
    parser.add_argument(
        "--trainer-level-percent",
        type=int,
        default=None,
        help=(
            "Scale trainer party levels (.lvl) by a percentage. "
            "Example: 25 increases levels by 25%%, -20 decreases by 20%%. "
            "Levels are clamped to 1..100."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    randomizer_dir = Path(__file__).resolve().parent
    repo_root = randomizer_dir.parent

    selected_any = args.all or args.wild or args.starters or args.trainers

    wild_level_percent = args.level_percent if args.wild_level_percent is None else args.wild_level_percent
    trainer_level_percent = (
        args.level_percent if args.trainer_level_percent is None else args.trainer_level_percent
    )

    restore_originals(randomizer_dir, repo_root)

    if args.restore:
        # Allow "restore + level scaling" as a convenience mode (used by the GUI):
        # when no randomization targets are selected, apply only the requested
        # level scaling on top of the restored (template) files.
        if not selected_any and (wild_level_percent != 0 or trainer_level_percent != 0):
            if wild_level_percent != 0:
                encounters_path = repo_root / "src/data/wild_encounters.json"
                encounters = encounters_path.read_text()
                encounters = scale_wild_levels_json(encounters, wild_level_percent)
                encounters_path.write_text(encounters)

            if trainer_level_percent != 0:
                parties_path = repo_root / "src/data/trainer_parties.h"
                parties = parties_path.read_text()
                parties = scale_trainer_party_levels(parties, trainer_level_percent)
                parties_path.write_text(parties)
        return

    do_wild = args.all or (args.wild if selected_any else True)
    do_starters = args.all or (args.starters if selected_any else True)
    do_trainers = args.all or (args.trainers if selected_any else True)

    # open species.txt and read all pokemon
    species_path = randomizer_dir / "species.txt"
    all_species = [line.strip() for line in species_path.read_text().splitlines() if line.strip()]

    if do_wild:
        encounters = (randomizer_dir / "wild_encounters.json").read_text()
        if args.per_map_consistent:
            encounters = randomize_wild_encounters_per_map(encounters, all_species)
        else:
            encounters = randomize_species_in_text(encounters, all_species, per_occurrence=args.per_occurrence)

        encounters = scale_wild_levels_json(encounters, wild_level_percent)
        (repo_root / "src/data/wild_encounters.json").write_text(encounters)

    if do_starters:
        starter_code = (randomizer_dir / "starter_choose.c").read_text()
        starter_code = randomize_species_in_text(starter_code, all_species, per_occurrence=args.per_occurrence)
        (repo_root / "src/starter_choose.c").write_text(starter_code)

    if do_trainers:
        trainer_parties = (randomizer_dir / "trainer_parties.h").read_text()
        trainer_parties = randomize_species_in_text(trainer_parties, all_species, per_occurrence=args.per_occurrence)
        trainer_parties = scale_trainer_party_levels(trainer_parties, trainer_level_percent)
        trainer_parties = convert_custom_moves_trainer_parties_to_default_moves(trainer_parties)
        (repo_root / "src/data/trainer_parties.h").write_text(trainer_parties)

        # Trainer definitions (switch party flags/macros to match converted parties)
        trainers = (randomizer_dir / "trainers.h").read_text()
        trainers = convert_trainers_to_default_moves(trainers)
        (repo_root / "src/data/trainers.h").write_text(trainers)


if __name__ == "__main__":
    main()