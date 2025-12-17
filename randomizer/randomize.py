import argparse
import random
import re
import subprocess
import sys
from pathlib import Path


RANDOMIZE_SPECIES_PATTERN = re.compile(r"\bSPECIES_[A-Z0-9_]+\b")
MOVES_FIELD_PATTERN = re.compile(r"(?m)^\s*\.moves\s*=\s*\{[^}]*\}\s*,?\s*$\n?")


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


def randomize_species_in_text(text: str, all_species: list[str]) -> str:
    mapping: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in ("SPECIES_NONE", "SPECIES_EGG"):
            return token
        if token not in mapping:
            mapping[token] = random.choice(all_species)
        return mapping[token]

    return RANDOMIZE_SPECIES_PATTERN.sub(repl, text)


def restore_originals(randomizer_dir: Path, repo_root: Path) -> None:
    targets = (
        "src/data/wild_encounters.json",
        "src/starter_choose.c",
        "src/data/trainer_parties.h",
        "src/data/trainers.h",
    )

    # Prefer restoring tracked files via git (keeps templates small and stays correct).
    if (repo_root / ".git").exists():
        subprocess.run(["git", "checkout", "--", *targets], cwd=repo_root, check=True)
        return

    # Fallback: restore from templates in randomizer/.
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
        "--restore",
        action="store_true",
        help="Restore original (unrandomized) files from randomizer/ templates.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    randomizer_dir = Path(__file__).resolve().parent
    repo_root = randomizer_dir.parent

    if args.restore:
        try:
            restore_originals(randomizer_dir, repo_root)
        except subprocess.CalledProcessError as e:
            print(f"restore failed: {e}", file=sys.stderr)
            raise
        return

    # open species.txt and read all pokemon
    species_path = randomizer_dir / "species.txt"
    all_species = [line.strip() for line in species_path.read_text().splitlines() if line.strip()]

    # Wild encounters
    encounters = (randomizer_dir / "wild_encounters.json").read_text()
    encounters = randomize_species_in_text(encounters, all_species)
    (repo_root / "src/data/wild_encounters.json").write_text(encounters)

    # Starters
    starter_code = (randomizer_dir / "starter_choose.c").read_text()
    starter_code = randomize_species_in_text(starter_code, all_species)
    (repo_root / "src/starter_choose.c").write_text(starter_code)

    # Enemy trainer parties
    trainer_parties = (randomizer_dir / "trainer_parties.h").read_text()
    trainer_parties = randomize_species_in_text(trainer_parties, all_species)
    trainer_parties = convert_custom_moves_trainer_parties_to_default_moves(trainer_parties)
    (repo_root / "src/data/trainer_parties.h").write_text(trainer_parties)

    # Trainer definitions (switch party flags/macros to match converted parties)
    trainers = (randomizer_dir / "trainers.h").read_text()
    trainers = convert_trainers_to_default_moves(trainers)
    (repo_root / "src/data/trainers.h").write_text(trainers)


if __name__ == "__main__":
    main()