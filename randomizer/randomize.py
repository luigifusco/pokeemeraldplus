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


def _compute_indegree(mapping: dict[str, str]) -> dict[str, int]:
    indeg: dict[str, int] = {s: 0 for s in mapping}
    for t in mapping.values():
        indeg[t] = indeg.get(t, 0) + 1
    return indeg


def _random_mapping(all_species: list[str]) -> dict[str, str]:
    """Start from a completely random functional graph (no self-loops)."""
    mapping: dict[str, str] = {}
    for s in all_species:
        t = random.choice(all_species)
        while t == s and len(all_species) > 1:
            t = random.choice(all_species)
        mapping[s] = t
    return mapping


# -- Local transformations -------------------------------------------------
#
# Every rule below preserves the "functional graph" shape (every node has
# out-degree exactly 1) and never creates a self-loop.

def _rule_reduce_indegree(
    mapping: dict[str, str], A: str, all_species: list[str], max_indegree: int
) -> bool:
    """Rule 1: reduce the in-degree of A by redirecting one predecessor B
    (currently B -> A) to a tail (a node with in-degree 0, which has the
    most room to accept a new edge). Falls back to any node still below
    the cap if no tails exist."""
    indeg = _compute_indegree(mapping)
    preds = [s for s, t in mapping.items() if t == A]
    if not preds:
        return False
    random.shuffle(preds)
    tails = [n for n in all_species if indeg[n] == 0]
    random.shuffle(tails)
    for B in preds:
        for T in tails:
            if T != B:
                mapping[B] = T
                return True
        # No tail available: accept any node whose in-degree is < cap - 1
        # (so it stays <= cap - 1 + 1 = cap after the redirect).
        room = [n for n in all_species if n != B and n != A and indeg[n] < max_indegree]
        if room:
            mapping[B] = random.choice(room)
            return True
    return False


def _rule_extend_cycle(
    mapping: dict[str, str], cycle: list[str], all_species: list[str]
) -> bool:
    """Rule 2: lengthen a cycle by splicing a tail into it. Given cycle
    edge X -> Y and a tail T (in-degree 0, not in the cycle), rewrite to
    X -> T -> Y. T's previous target W loses one in-degree (it was a
    tree/cycle node feeding wherever, now T simply re-routes). This
    preserves max_indegree bounds because T gains 1 (goes from 0 to 1)
    and no other in-degree grows."""
    indeg = _compute_indegree(mapping)
    cycset = set(cycle)
    tails = [n for n in all_species if indeg[n] == 0 and n not in cycset]
    if not tails:
        return False
    T = random.choice(tails)
    L = len(cycle)
    i = random.randrange(L)
    X = cycle[i]
    Y = cycle[(i + 1) % L]
    if T == Y:
        # T already equals the successor; can't self-loop.
        return False
    mapping[X] = T
    mapping[T] = Y
    return True


def _rule_merge_cycles(
    mapping: dict[str, str], cycle_a: list[str], cycle_b: list[str]
) -> bool:
    """Rule 4: merge two cycles into one via an inter-cycle edge swap.

    Inverse of rule 3. Given edges X -> Y in cycle A and P -> Q in cycle
    B, swap targets: X -> Q, P -> Y. The result is a single cycle whose
    length is len(A) + len(B). Every node's in-degree is preserved.

    Used to grow cycle length (for min_cycle_length) when no tails are
    available to splice in via rule 2.
    """
    if not cycle_a or not cycle_b:
        return False
    La, Lb = len(cycle_a), len(cycle_b)
    i = random.randrange(La)
    j = random.randrange(Lb)
    X = cycle_a[i]
    Y = cycle_a[(i + 1) % La]
    P = cycle_b[j]
    Q = cycle_b[(j + 1) % Lb]
    if X == Q or P == Y:
        return False
    mapping[X] = Q
    mapping[P] = Y
    return True


def _rule_split_cycle(
    mapping: dict[str, str], cycle: list[str], target_max: int | None
) -> bool:
    """Rule 3: swap two edges inside one cycle to split it in two.

    Cycle n0 -> n1 -> ... -> n(L-1) -> n0. Picking edges n_i -> n_(i+1)
    and n_j -> n_(j+1) and swapping their targets gives two cycles of
    length k = j - i and L - k. Every node's in-degree is preserved.
    Disallows length-1 halves (self-loops are forbidden)."""
    L = len(cycle)
    if L < 4:
        return False
    if target_max is not None:
        lo = max(2, L - target_max)
        hi = min(L - 2, target_max)
        if lo > hi:
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
    if a == d or c == b:
        return False
    mapping[a] = d
    mapping[c] = b
    return True


def _pick_constrained_mapping(
    all_species: list[str],
    *,
    max_indegree: int | None,
    max_cycle_length: int | None,
    min_cycles: int | None,
    min_cycle_length: int | None = None,
    max_avg_indegree: float | None = None,
) -> dict[str, str]:
    """Start from a random mapping and repair until constraints hold.

    Repair rules (all local, all preserve the functional-graph shape;
    none ever produces a self-loop):
      1. _rule_reduce_indegree: if node A has too many predecessors,
         redirect one predecessor B to a tail (a node with in-degree 0).
         Also used to lower the *average* in-degree of non-tail nodes:
         every application turns one tail into a target (+1 distinct
         target), so N / num_distinct_targets strictly decreases.
      2. _rule_extend_cycle: splice a tail into a cycle (cycle length
         +1). Used to lengthen a short cycle for min_cycle_length or to
         make a too-short cycle splittable for min_cycles.
      3. _rule_split_cycle: intra-cycle edge swap; splits one cycle of
         length L into lengths k and L-k, preserving in-degrees. Used
         to shrink long cycles and raise the cycle count.
      4. _rule_merge_cycles: inter-cycle edge swap; merges cycles A and
         B into one of length len(A)+len(B), preserving in-degrees.
         Used to grow cycle length when no tails remain for rule 2.
    """
    if max_cycle_length is not None and max_cycle_length < 2:
        raise RuntimeError("max_cycle_length must be >= 2 (no self-loops allowed).")
    if min_cycle_length is not None and min_cycle_length < 2:
        raise RuntimeError("min_cycle_length must be >= 2 (no self-loops allowed).")
    if (
        max_cycle_length is not None
        and min_cycle_length is not None
        and min_cycle_length > max_cycle_length
    ):
        raise RuntimeError("min_cycle_length must be <= max_cycle_length.")

    mapping = _random_mapping(all_species)
    N = len(all_species)
    budget = N * 50

    def _avg_indeg(indeg: dict[str, int]) -> float:
        # Average in-degree over non-tail nodes = N / num_distinct_targets.
        distinct = sum(1 for d in indeg.values() if d > 0)
        return (N / distinct) if distinct else 0.0

    for _ in range(budget):
        indeg = _compute_indegree(mapping)

        # Rule 1: squash any in-degree violation first.
        if max_indegree is not None:
            over = [n for n, d in indeg.items() if d > max_indegree]
            if over:
                A = random.choice(over)
                _rule_reduce_indegree(mapping, A, all_species, max_indegree)
                continue

        # Rule 1 again: lower average in-degree if above the cap. Pick
        # the node with the highest in-degree and bleed an edge off to
        # a tail (turns a 0 into a 1, improving the ratio).
        if max_avg_indegree is not None and _avg_indeg(indeg) > max_avg_indegree:
            # Effective per-node cap used by rule 1's fallback path.
            cap = max_indegree if max_indegree is not None else N
            heaviest = max(indeg, key=lambda n: indeg[n])
            if indeg[heaviest] >= 2:
                _rule_reduce_indegree(mapping, heaviest, all_species, cap)
                continue
            # Everything is already at indeg 1; can't reduce further.
            break

        cycles = _find_cycles(mapping)

        # Rule 3: shrink any cycle longer than max_cycle_length.
        if max_cycle_length is not None:
            too_long = [c for c in cycles if len(c) > max_cycle_length]
            if too_long:
                cyc = max(too_long, key=len)
                if _rule_split_cycle(mapping, cyc, target_max=max_cycle_length):
                    continue
                if _rule_extend_cycle(mapping, cyc, all_species):
                    continue
                break

        # Rule 2/4: grow any cycle shorter than min_cycle_length.
        if min_cycle_length is not None:
            too_short = [c for c in cycles if len(c) < min_cycle_length]
            if too_short:
                cyc = random.choice(too_short)
                if _rule_extend_cycle(mapping, cyc, all_species):
                    continue
                # No tails available: merge with another cycle.
                others = [c for c in cycles if c is not cyc]
                if others:
                    other = random.choice(others)
                    if _rule_merge_cycles(mapping, cyc, other):
                        continue
                break

        # Rule 3/2: raise the cycle count by splitting cycles.
        if min_cycles is not None and len(cycles) < min_cycles:
            splittable = [
                c for c in cycles
                if len(c) >= 4
                and (
                    min_cycle_length is None
                    or len(c) >= 2 * min_cycle_length
                )
            ]
            if splittable:
                cyc = max(splittable, key=len)
                if _rule_split_cycle(mapping, cyc, target_max=max_cycle_length):
                    continue
            # No cycle long enough to split: grow a short one first.
            growable = [c for c in cycles if len(c) < 4]
            random.shuffle(growable)
            did = False
            for cyc in growable:
                if _rule_extend_cycle(mapping, cyc, all_species):
                    did = True
                    break
            if did:
                continue
            break

        return mapping

    # Final validation: report any constraint we failed to satisfy.
    indeg = _compute_indegree(mapping)
    cycles = _find_cycles(mapping)
    if max_indegree is not None and max(indeg.values(), default=0) > max_indegree:
        raise RuntimeError(
            f"Could not enforce max_indegree={max_indegree} "
            f"(worst in-degree = {max(indeg.values())})."
        )
    if max_avg_indegree is not None and _avg_indeg(indeg) > max_avg_indegree + 1e-9:
        raise RuntimeError(
            f"Could not enforce max_avg_indegree={max_avg_indegree} "
            f"(achieved {_avg_indeg(indeg):.3f})."
        )
    if max_cycle_length is not None and any(len(c) > max_cycle_length for c in cycles):
        raise RuntimeError(
            f"Could not reduce max cycle length to {max_cycle_length} "
            f"(longest remaining cycle = {max(len(c) for c in cycles)})."
        )
    if min_cycle_length is not None and any(len(c) < min_cycle_length for c in cycles):
        raise RuntimeError(
            f"Could not enforce min_cycle_length={min_cycle_length} "
            f"(shortest remaining cycle = {min(len(c) for c in cycles)})."
        )
    if min_cycles is not None and len(cycles) < min_cycles:
        raise RuntimeError(
            f"Could not reach min_cycles={min_cycles} "
            f"(achieved {len(cycles)})."
        )
    return mapping


def generate_hardcoded_random_evolutions_header(
    all_species: list[str],
    header_path: Path,
    *,
    max_indegree: int | None = None,
    max_cycle_length: int | None = None,
    min_cycles: int | None = None,
    min_cycle_length: int | None = None,
    max_avg_indegree: float | None = None,
) -> None:
    if (
        max_indegree is None
        and max_cycle_length is None
        and min_cycles is None
        and min_cycle_length is None
        and max_avg_indegree is None
    ):
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
            min_cycle_length=min_cycle_length,
            max_avg_indegree=max_avg_indegree,
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
    parser.add_argument(
        "--evo-min-cycle-length",
        type=int,
        default=None,
        help=(
            "When generating hardcoded random evolutions, require every cycle in the "
            "evolution graph to be at least this long."
        ),
    )
    parser.add_argument(
        "--evo-max-avg-indegree",
        type=float,
        default=None,
        help=(
            "When generating hardcoded random evolutions, cap the average in-degree "
            "computed over target species (nodes with in-degree > 0). Lower values "
            "force edges to be spread across more distinct targets."
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
            min_cycle_length=args.evo_min_cycle_length,
            max_avg_indegree=args.evo_max_avg_indegree,
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