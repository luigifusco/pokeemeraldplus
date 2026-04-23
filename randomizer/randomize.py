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


def _find_cycles(mapping: dict[str, str]) -> list[list[str]]:
    """Return list of cycles in the functional graph, each in traversal order."""
    state: dict[str, int] = {}
    cycles: list[list[str]] = []
    for start in mapping:
        if start in state:
            continue
        path: list[str] = []
        pos: dict[str, int] = {}
        node: str | None = start
        while node is not None and node not in state:
            state[node] = 1
            pos[node] = len(path)
            path.append(node)
            node = mapping.get(node)
        if node is not None and state.get(node) == 1:
            cycles.append(path[pos[node]:])
        for n in path:
            state[n] = 2
    return cycles


def _build_initial_mapping(
    all_species: list[str], max_indegree: int | None
) -> dict[str, str]:
    """Assign each species to a random target, respecting max_indegree."""
    limit = max_indegree if max_indegree is not None else len(all_species)
    if limit < 1:
        raise RuntimeError("max_indegree must be >= 1")
    mapping: dict[str, str] = {}
    indeg: dict[str, int] = {s: 0 for s in all_species}
    order = all_species[:]
    random.shuffle(order)
    # Hard to paint yourself into a corner with a greedy walk when
    # average target in-degree == 1, but with a tight cap it can happen
    # (e.g. last remaining species is the only one under the cap but it's
    # the source itself). Retry a handful of times on failure.
    for attempt in range(50):
        mapping.clear()
        for s in all_species:
            indeg[s] = 0
        random.shuffle(order)
        ok = True
        for src in order:
            cands = [t for t in all_species if t != src and indeg[t] < limit]
            if not cands:
                ok = False
                break
            t = random.choice(cands)
            mapping[src] = t
            indeg[t] += 1
        if ok:
            return mapping
    raise RuntimeError(
        f"Could not build a mapping with max_indegree={max_indegree} "
        f"over {len(all_species)} species."
    )


def _split_cycle(mapping: dict[str, str], cycle: list[str], target_max: int | None) -> bool:
    """Swap two edges inside `cycle` to split it in two.

    In a functional graph, a cycle n0 -> n1 -> ... -> n(L-1) -> n0 can be
    split by picking two edges n_i -> n_(i+1) and n_j -> n_(j+1) and
    swapping their targets: n_i -> n_(j+1), n_j -> n_(i+1). The result is
    two cycles of lengths k = j - i and L - k (mod L). This preserves
    every node's in-degree (each new target is one cycle member's
    successor by construction).

    Returns True if a split was performed. Disallows length-1 halves
    (which would create a self-loop -> src == target is forbidden).
    """
    L = len(cycle)
    if L < 4:
        return False  # Can't split into two halves of length >= 2.
    if target_max is not None:
        # Try to keep both halves <= target_max first.
        lo = max(2, L - target_max)
        hi = min(L - 2, target_max)
        if lo > hi:
            # Impossible to make both halves <= target_max in one split;
            # pick any valid split -- further splits will shorten further.
            lo, hi = 2, L - 2
    else:
        lo, hi = 2, L - 2
    k = random.randint(lo, hi)
    i = random.randrange(L)
    j = (i + k) % L
    a = cycle[i]
    b = cycle[(i + 1) % L]
    c = cycle[j]
    d = cycle[(j + 1) % L]
    mapping[a] = d
    mapping[c] = b
    return True


def _pick_constrained_mapping(
    all_species: list[str],
    *,
    max_indegree: int | None,
    max_cycle_length: int | None,
    min_cycles: int | None,
) -> dict[str, str]:
    """Build a random species -> species mapping respecting optional constraints.

    Strategy:
      1. Build a random initial mapping that respects max_indegree by
         choosing each source's target from species still under the cap.
      2. Repeatedly split cycles longer than max_cycle_length with an
         intra-cycle edge swap (which preserves all in-degrees).
      3. If the total cycle count is below min_cycles, keep splitting
         the longest splittable cycle (length >= 4) to create more
         separate loops.
    """
    if max_cycle_length is not None and max_cycle_length < 2:
        raise RuntimeError("max_cycle_length must be >= 2 (no self-loops allowed).")

    mapping = _build_initial_mapping(all_species, max_indegree)
    N = len(all_species)

    if max_cycle_length is not None:
        for _ in range(N):
            cycles = _find_cycles(mapping)
            long_cycles = [c for c in cycles if len(c) > max_cycle_length]
            if not long_cycles:
                break
            cyc = max(long_cycles, key=len)
            if not _split_cycle(mapping, cyc, target_max=max_cycle_length):
                break

    if min_cycles is not None:
        for _ in range(N):
            cycles = _find_cycles(mapping)
            if len(cycles) >= min_cycles:
                break
            splittable = [c for c in cycles if len(c) >= 4]
            if not splittable:
                break
            cyc = max(splittable, key=len)
            _split_cycle(mapping, cyc, target_max=max_cycle_length)

    # Sanity-check constraints; report what went wrong if unsatisfiable.
    cycles = _find_cycles(mapping)
    if max_cycle_length is not None and any(len(c) > max_cycle_length for c in cycles):
        raise RuntimeError(
            f"Could not reduce max cycle length to {max_cycle_length} "
            f"(longest remaining cycle = {max(len(c) for c in cycles)})."
        )
    if min_cycles is not None and len(cycles) < min_cycles:
        raise RuntimeError(
            f"Could not reach min_cycles={min_cycles} "
            f"(achieved {len(cycles)}; all remaining cycles are too short to split)."
        )
    return mapping


def generate_hardcoded_random_evolutions_header(
    all_species: list[str],
    header_path: Path,
    *,
    max_indegree: int | None = None,
    max_cycle_length: int | None = None,
    min_cycles: int | None = None,
) -> None:
    if max_indegree is None and max_cycle_length is None and min_cycles is None:
        mapping: dict[str, str] = {}
        for s in all_species:
            target = random.choice(all_species)
            while target == s and len(all_species) > 1:
                target = random.choice(all_species)
            mapping[s] = target
    else:
        mapping = _pick_constrained_mapping(
            all_species,
            max_indegree=max_indegree,
            max_cycle_length=max_cycle_length,
            min_cycles=min_cycles,
        )

    lines = [
        "// Auto-generated by randomizer/randomize.py. Do not edit by hand.",
        "// Maps each species ID to a hardcoded random evolution target.",
        "#ifndef GUARD_DATA_RANDOM_EVOLUTIONS_H",
        "#define GUARD_DATA_RANDOM_EVOLUTIONS_H",
        "",
        "static const u16 sHardcodedRandomEvolutionTable[NUM_SPECIES] = {",
    ]
    for s in all_species:
        lines.append(f"    [{s}] = {mapping[s]},")
    lines += [
        "};",
        "",
        "#endif // GUARD_DATA_RANDOM_EVOLUTIONS_H",
        "",
    ]
    header_path.parent.mkdir(parents=True, exist_ok=True)
    header_path.write_text("\n".join(lines))


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
    parser.add_argument(
        "--hardcoded-random-evos",
        action="store_true",
        help=(
            "Generate src/data/random_evolutions.h with a random evolution mapping "
            "for every species. Used with the HARDCODED_RANDOM_EVOLUTIONS build flag."
        ),
    )
    parser.add_argument(
        "--evo-max-indegree",
        type=int,
        default=None,
        help=(
            "When generating hardcoded random evolutions, cap the number of species "
            "that may evolve into any given target species."
        ),
    )
    parser.add_argument(
        "--evo-max-cycle-length",
        type=int,
        default=None,
        help=(
            "When generating hardcoded random evolutions, cap the length of any cycle "
            "in the evolution graph (e.g. 1 forbids cycles entirely is impossible since "
            "a functional graph always has a cycle; 2 allows only A<->B pairs; etc.)."
        ),
    )
    parser.add_argument(
        "--evo-min-cycles",
        type=int,
        default=None,
        help=(
            "When generating hardcoded random evolutions, require at least this many "
            "distinct cycles in the evolution graph."
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

    # open species.txt and read all pokemon
    species_path = randomizer_dir / "species.txt"
    all_species = [line.strip() for line in species_path.read_text().splitlines() if line.strip()]

    # Generate hardcoded random evolutions header if requested, otherwise
    # ensure a default mapping exists so builds always compile.
    random_evos_header = repo_root / "src/data/random_evolutions.h"
    if args.hardcoded_random_evos:
        generate_hardcoded_random_evolutions_header(
            all_species,
            random_evos_header,
            max_indegree=args.evo_max_indegree,
            max_cycle_length=args.evo_max_cycle_length,
            min_cycles=args.evo_min_cycles,
        )
    elif not random_evos_header.exists():
        default_lines = [
            "// Auto-generated default. Regenerate with randomizer/randomize.py --hardcoded-random-evos.",
            "#ifndef GUARD_DATA_RANDOM_EVOLUTIONS_H",
            "#define GUARD_DATA_RANDOM_EVOLUTIONS_H",
            "",
            "static const u16 sHardcodedRandomEvolutionTable[NUM_SPECIES] = {0};",
            "",
            "#endif // GUARD_DATA_RANDOM_EVOLUTIONS_H",
            "",
        ]
        random_evos_header.parent.mkdir(parents=True, exist_ok=True)
        random_evos_header.write_text("\n".join(default_lines))

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