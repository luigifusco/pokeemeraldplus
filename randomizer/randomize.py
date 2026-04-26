import argparse
from datetime import datetime, timezone
import json
import random
import re
import sys
from pathlib import Path


RANDOMIZE_SPECIES_PATTERN = re.compile(r"\bSPECIES_[A-Z0-9_]+\b")
MOVES_FIELD_PATTERN = re.compile(r"(?m)^\s*\.moves\s*=\s*\{[^}]*\}\s*,?\s*$\n?")
TRAINER_LVL_PATTERN = re.compile(r"(?m)(^\s*\.lvl\s*=\s*)(\d+)(\s*,)")
MOVE_DEFINE_PATTERN = re.compile(r"^#define\s+(MOVE_[A-Z0-9_]+)\s+(\d+)\b", re.MULTILINE)
MOVE_BLOCK_PATTERN = re.compile(r"\[(MOVE_[A-Z0-9_]+)\]\s*=\s*\{(.*?)\n\s*\},", re.DOTALL)
SPECIES_INFO_BLOCK_PATTERN = re.compile(
    r"^\s*\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*(?:\{([^\n{}]*)\},|\{(.*?)^\s*\},)",
    re.DOTALL | re.MULTILINE,
)
LEVEL_UP_BLOCK_PATTERN = re.compile(
    r"static const u16 (s[A-Za-z0-9_]+LevelUpLearnset)\[\] = \{\n(.*?)\n\};",
    re.DOTALL,
)
LEVEL_UP_ENTRY_PATTERN = re.compile(r"LEVEL_UP_MOVE\(\s*(\d+)\s*,\s*(MOVE_[A-Z0-9_]+)\s*\)")
LEVEL_UP_POINTER_PATTERN = re.compile(
    r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*(s[A-Za-z0-9_]+LevelUpLearnset)"
)
EGG_MOVES_BLOCK_PATTERN = re.compile(r"    egg_moves\(([A-Z0-9_]+),\n(.*?)\)", re.DOTALL)
TMHM_LEARNSET_BLOCK_PATTERN = re.compile(
    r"    \[(SPECIES_[A-Z0-9_]+)\]\s*=\s*\{ \.learnset = \{\n(.*?)\n    \} \},",
    re.DOTALL,
)
TUTOR_MOVE_ENTRY_PATTERN = re.compile(r"\[(TUTOR_MOVE_[A-Z0-9_]+)\]\s*=\s*(MOVE_[A-Z0-9_]+)")
TUTOR_LEARNSET_BLOCK_PATTERN = re.compile(
    r"    \[(SPECIES_[A-Z0-9_]+)\]\s*=\s*\((.*?)\),",
    re.DOTALL,
)

SPECIAL_TYPES = {
    "TYPE_FIRE",
    "TYPE_WATER",
    "TYPE_GRASS",
    "TYPE_ELECTRIC",
    "TYPE_PSYCHIC",
    "TYPE_ICE",
    "TYPE_DRAGON",
    "TYPE_DARK",
}
ALWAYS_BANNED_MOVES = {
    "MOVE_NONE",
    "MOVE_STRUGGLE",
}
BROKEN_MOVE_EFFECTS = {
    "EFFECT_OHKO",
    "EFFECT_EXPLOSION",
    "EFFECT_TELEPORT",
    "EFFECT_MEMENTO",
    "EFFECT_PERISH_SONG",
}
GOOD_DAMAGING_MIN_ACCURACY = 70


def _clamp_percent(value: int) -> int:
    return max(0, min(100, value))


def _clamp_level(level: int) -> int:
    return max(1, min(100, level))


def _scale_level(level: int, percent: int) -> int:
    factor = 1.0 + (percent / 100.0)
    return _clamp_level(int(round(level * factor)))


def _adjust_level(level: int, percent: int, fixed_level: int | None) -> int:
    if fixed_level is not None:
        return _clamp_level(fixed_level)
    return _scale_level(level, percent)


def scale_wild_levels_json(text: str, percent: int, fixed_level: int | None = None) -> str:
    if percent == 0 and fixed_level is None:
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
                        mon["min_level"] = _adjust_level(mon["min_level"], percent, fixed_level)
                    if "max_level" in mon and isinstance(mon["max_level"], int):
                        mon["max_level"] = _adjust_level(mon["max_level"], percent, fixed_level)
                    if (
                        fixed_level is None
                        and "min_level" in mon
                        and "max_level" in mon
                        and isinstance(mon["min_level"], int)
                        and isinstance(mon["max_level"], int)
                        and mon["min_level"] > mon["max_level"]
                    ):
                        mon["min_level"], mon["max_level"] = mon["max_level"], mon["min_level"]

    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def scale_trainer_party_levels(text: str, percent: int, fixed_level: int | None = None) -> str:
    if percent == 0 and fixed_level is None:
        return text

    def repl(match: re.Match[str]) -> str:
        prefix, lvl_str, suffix = match.groups()
        new_lvl = _adjust_level(int(lvl_str), percent, fixed_level)
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


def _field_value(block: str, field: str) -> str | None:
    match = re.search(rf"\.{field}\s*=\s*([^,\n}}]+)", block)
    return match.group(1).strip() if match else None


def _parse_int_field(block: str, field: str, default: int = 0) -> int:
    value = _field_value(block, field)
    if value is None:
        return default
    try:
        return int(value, 0)
    except ValueError:
        return default


def parse_move_constants(text: str) -> list[str]:
    moves: list[tuple[int, str]] = []
    for name, value in MOVE_DEFINE_PATTERN.findall(text):
        if name in ("MOVE_UNAVAILABLE",):
            continue
        moves.append((int(value), name))
    return [name for _, name in sorted(moves)]


def parse_battle_moves(text: str) -> dict[str, dict[str, object]]:
    moves: dict[str, dict[str, object]] = {}
    for move, block in MOVE_BLOCK_PATTERN.findall(text):
        moves[move] = {
            "effect": _field_value(block, "effect") or "",
            "power": _parse_int_field(block, "power"),
            "type": _field_value(block, "type") or "TYPE_NORMAL",
            "accuracy": _parse_int_field(block, "accuracy", 100),
        }
    return moves


def parse_species_info(text: str) -> dict[str, dict[str, object]]:
    species: dict[str, dict[str, object]] = {}
    for species_token, one_line_block, multi_line_block in SPECIES_INFO_BLOCK_PATTERN.findall(text):
        block = multi_line_block or one_line_block
        types_match = re.search(r"\.types\s*=\s*\{\s*(TYPE_[A-Z_]+)\s*,\s*(TYPE_[A-Z_]+)\s*\}", block)
        if not types_match:
            continue
        species[species_token] = {
            "attack": _parse_int_field(block, "baseAttack", 50),
            "sp_attack": _parse_int_field(block, "baseSpAttack", 50),
            "types": (types_match.group(1), types_match.group(2)),
        }
    return species


def _parse_foreach_items(text: str, macro_name: str, stop_macro: str) -> list[str]:
    match = re.search(
        rf"#define {macro_name}\(F\) \\\n(.*?)(?=\n#define {stop_macro})",
        text,
        re.DOTALL,
    )
    if not match:
        return []
    return re.findall(r"F\(([A-Z0-9_]+)\)", match.group(1))


def parse_tmhm_ids(text: str) -> tuple[list[str], list[str]]:
    return (
        _parse_foreach_items(text, "FOREACH_TM", "FOREACH_HM"),
        _parse_foreach_items(text, "FOREACH_HM", "FOREACH_TMHM"),
    )


def _format_foreach_tm(tm_ids: list[str]) -> str:
    lines = ["#define FOREACH_TM(F) \\"]
    for i, tm_id in enumerate(tm_ids):
        suffix = " \\" if i != len(tm_ids) - 1 else ""
        lines.append(f"    F({tm_id}){suffix}")
    return "\n".join(lines)


def replace_foreach_tm(text: str, tm_ids: list[str]) -> str:
    return re.sub(
        r"#define FOREACH_TM\(F\) \\\n.*?(?=\n#define FOREACH_HM)",
        _format_foreach_tm(tm_ids),
        text,
        flags=re.DOTALL,
    )


def parse_tutor_moves(text: str) -> list[tuple[str, str]]:
    return [(slot, move) for slot, move in TUTOR_MOVE_ENTRY_PATTERN.findall(text)]


def _is_special_move(move: str, move_data: dict[str, dict[str, object]]) -> bool:
    return move_data.get(move, {}).get("type") in SPECIAL_TYPES


def _is_good_damaging(move: str, move_data: dict[str, dict[str, object]]) -> bool:
    info = move_data.get(move)
    if not info:
        return False
    return (
        int(info.get("power", 0)) > 1
        and int(info.get("accuracy", 0)) >= GOOD_DAMAGING_MIN_ACCURACY
        and info.get("effect") not in BROKEN_MOVE_EFFECTS
    )


def _valid_moves(
    all_moves: list[str],
    move_data: dict[str, dict[str, object]],
    *,
    no_broken: bool,
    excluded_moves: set[str] | None = None,
) -> list[str]:
    excluded = set(excluded_moves or set())
    excluded.update(ALWAYS_BANNED_MOVES)
    if no_broken:
        excluded.update(
            move for move, info in move_data.items()
            if info.get("effect") in BROKEN_MOVE_EFFECTS
        )
    return [
        move for move in all_moves
        if move in move_data and move not in excluded
    ]


def _move_type(move: str, move_data: dict[str, dict[str, object]]) -> str | None:
    value = move_data.get(move, {}).get("type")
    return value if isinstance(value, str) else None


def _unused(pool: list[str], learnt: set[str]) -> list[str]:
    return [move for move in pool if move not in learnt]


def _species_type_choice(species: dict[str, object] | None) -> str | None:
    if not species:
        return None
    types = tuple(t for t in species.get("types", ()) if t != "TYPE_NONE")
    if not types:
        return None
    primary = types[0]
    secondary = types[1] if len(types) > 1 else primary
    if secondary == primary:
        secondary = None

    roll = random.random()
    if secondary is None:
        return primary if roll < 0.4 else None
    if primary == "TYPE_NORMAL" or secondary == "TYPE_NORMAL":
        other = secondary if primary == "TYPE_NORMAL" else primary
        if roll < 0.1:
            return "TYPE_NORMAL"
        if roll < 0.4:
            return other
        return None
    if roll < 0.2:
        return primary
    if roll < 0.4:
        return secondary
    return None


def _attack_bias_pick_category(species: dict[str, object] | None) -> str | None:
    if not species:
        return None
    attack = max(1, int(species.get("attack", 50)))
    sp_attack = max(1, int(species.get("sp_attack", 50)))
    physical_chance = attack / (attack + sp_attack)
    return "physical" if random.random() < physical_chance else "special"


def _pick_random_move(
    *,
    valid_moves: list[str],
    good_damaging_moves: list[str],
    moves_by_type: dict[str, list[str]],
    good_moves_by_type: dict[str, list[str]],
    move_data: dict[str, dict[str, object]],
    species: dict[str, object] | None,
    learnt: set[str],
    prefer_same_type: bool,
    force_good_damaging: bool,
) -> str:
    pick_pool = valid_moves
    preferred_type = _species_type_choice(species) if prefer_same_type else None

    if force_good_damaging:
        if preferred_type and _unused(good_moves_by_type.get(preferred_type, []), learnt):
            pick_pool = good_moves_by_type[preferred_type]
        elif _unused(good_damaging_moves, learnt):
            pick_pool = good_damaging_moves

        category = _attack_bias_pick_category(species)
        if category:
            wants_special = category == "special"
            category_pool = [
                move for move in pick_pool
                if _is_special_move(move, move_data) == wants_special
            ]
            if _unused(category_pool, learnt):
                pick_pool = category_pool
    elif preferred_type and _unused(moves_by_type.get(preferred_type, []), learnt):
        pick_pool = moves_by_type[preferred_type]

    unused = _unused(pick_pool, learnt)
    if not unused:
        unused = _unused(valid_moves, learnt)
    if not unused:
        unused = valid_moves
    return random.choice(unused)


def _build_move_pools(
    valid_moves: list[str],
    move_data: dict[str, dict[str, object]],
) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    good_damaging_moves = [move for move in valid_moves if _is_good_damaging(move, move_data)]
    moves_by_type: dict[str, list[str]] = {}
    good_moves_by_type: dict[str, list[str]] = {}
    for move in valid_moves:
        move_type = _move_type(move, move_data)
        if move_type:
            moves_by_type.setdefault(move_type, []).append(move)
            if move in good_damaging_moves:
                good_moves_by_type.setdefault(move_type, []).append(move)
    return good_damaging_moves, moves_by_type, good_moves_by_type


def _randomized_move_list(
    count: int,
    species: dict[str, object] | None,
    valid_moves: list[str],
    move_data: dict[str, dict[str, object]],
    *,
    prefer_same_type: bool,
    good_damaging_percent: int,
    force_index_good: int | None = None,
) -> list[str]:
    good_damaging_moves, moves_by_type, good_moves_by_type = _build_move_pools(valid_moves, move_data)
    learnt: set[str] = set()
    picked: list[str] = []
    good_left = int(round((_clamp_percent(good_damaging_percent) / 100.0) * count))

    for i in range(count):
        force_good = (force_index_good is not None and i == force_index_good) or good_left > 0
        move = _pick_random_move(
            valid_moves=valid_moves,
            good_damaging_moves=good_damaging_moves,
            moves_by_type=moves_by_type,
            good_moves_by_type=good_moves_by_type,
            move_data=move_data,
            species=species,
            learnt=learnt,
            prefer_same_type=prefer_same_type,
            force_good_damaging=force_good,
        )
        picked.append(move)
        learnt.add(move)
        if force_index_good is None or i != force_index_good:
            good_left -= 1
    return picked


def randomize_level_up_learnsets(
    text: str,
    pointer_text: str,
    species_info: dict[str, dict[str, object]],
    valid_moves: list[str],
    move_data: dict[str, dict[str, object]],
    *,
    prefer_same_type: bool,
    good_damaging_percent: int,
    guaranteed_starting_moves: int,
) -> str:
    learnset_species = {
        learnset: species
        for species, learnset in LEVEL_UP_POINTER_PATTERN.findall(pointer_text)
        if species != "SPECIES_NONE"
    }

    def repl(match: re.Match[str]) -> str:
        learnset_name = match.group(1)
        body = match.group(2)
        species = learnset_species.get(learnset_name)
        entries = [(int(level), move) for level, move in LEVEL_UP_ENTRY_PATTERN.findall(body)]
        if not species or not entries:
            return match.group(0)

        levels = [level for level, _ in entries]
        if guaranteed_starting_moves > 0:
            lv1_count = sum(1 for level in levels if level == 1)
            insert_at = 0
            while insert_at < len(levels) and levels[insert_at] <= 1:
                insert_at += 1
            for _ in range(max(0, guaranteed_starting_moves - lv1_count)):
                levels.insert(insert_at, 1)
                insert_at += 1

        lv1_indices = [i for i, level in enumerate(levels) if level == 1]
        force_index = lv1_indices[-1] if lv1_indices else 0
        picked = _randomized_move_list(
            len(levels),
            species_info.get(species),
            valid_moves,
            move_data,
            prefer_same_type=prefer_same_type,
            good_damaging_percent=good_damaging_percent,
            force_index_good=force_index,
        )
        random.shuffle(picked)
        forced_move = picked[force_index]
        for i, move in enumerate(picked):
            if _is_good_damaging(move, move_data):
                forced_move = move
                break
        if picked[force_index] != forced_move:
            swap_index = picked.index(forced_move)
            picked[swap_index], picked[force_index] = picked[force_index], picked[swap_index]

        lines = [f"static const u16 {learnset_name}[] = {{"]
        for level, move in zip(levels, picked):
            lines.append(f"    LEVEL_UP_MOVE({level:2d}, {move}),")
        lines.append("    LEVEL_UP_END")
        lines.append("};")
        return "\n".join(lines)

    return LEVEL_UP_BLOCK_PATTERN.sub(repl, text)


def randomize_egg_moves(
    text: str,
    species_info: dict[str, dict[str, object]],
    valid_moves: list[str],
    move_data: dict[str, dict[str, object]],
    *,
    prefer_same_type: bool,
    good_damaging_percent: int,
) -> str:
    def repl(match: re.Match[str]) -> str:
        species_name = match.group(1)
        species = f"SPECIES_{species_name}"
        old_moves = re.findall(r"MOVE_[A-Z0-9_]+", match.group(2))
        if not old_moves or species not in species_info:
            return match.group(0)
        picked = _randomized_move_list(
            len(old_moves),
            species_info.get(species),
            valid_moves,
            move_data,
            prefer_same_type=prefer_same_type,
            good_damaging_percent=good_damaging_percent,
        )
        random.shuffle(picked)
        lines = [f"    egg_moves({species_name},"]
        for i, move in enumerate(picked):
            comma = "," if i != len(picked) - 1 else ""
            lines.append(f"              {move}{comma}")
        lines[-1] += ")"
        return "\n".join(lines)

    return EGG_MOVES_BLOCK_PATTERN.sub(repl, text)


def randomize_tm_moves(
    tms_hms_text: str,
    all_moves: list[str],
    move_data: dict[str, dict[str, object]],
    *,
    no_broken: bool,
    good_damaging_percent: int,
) -> str:
    tm_ids, hm_ids = parse_tmhm_ids(tms_hms_text)
    excluded = {f"MOVE_{hm_id}" for hm_id in hm_ids}
    valid = _valid_moves(all_moves, move_data, no_broken=no_broken, excluded_moves=excluded)
    good = [move for move in valid if _is_good_damaging(move, move_data)]
    picked: list[str] = []
    good_left = int(round((_clamp_percent(good_damaging_percent) / 100.0) * len(tm_ids)))
    for _ in tm_ids:
        pool = good if good_left > 0 and _unused(good, set(picked)) else valid
        move = random.choice(_unused(pool, set(picked)))
        picked.append(move)
        good_left -= 1
    random.shuffle(picked)
    return replace_foreach_tm(tms_hms_text, [move.removeprefix("MOVE_") for move in picked])


def randomize_tutor_moves(
    text: str,
    all_moves: list[str],
    move_data: dict[str, dict[str, object]],
    tms_hms_text: str,
    *,
    no_broken: bool,
    good_damaging_percent: int,
) -> str:
    tutor_slots = parse_tutor_moves(text)
    tm_ids, hm_ids = parse_tmhm_ids(tms_hms_text)
    excluded = {f"MOVE_{move_id}" for move_id in tm_ids + hm_ids}
    valid = _valid_moves(all_moves, move_data, no_broken=no_broken, excluded_moves=excluded)
    good = [move for move in valid if _is_good_damaging(move, move_data)]
    picked: list[str] = []
    good_left = int(round((_clamp_percent(good_damaging_percent) / 100.0) * len(tutor_slots)))
    for _ in tutor_slots:
        pool = good if good_left > 0 and _unused(good, set(picked)) else valid
        move = random.choice(_unused(pool, set(picked)))
        picked.append(move)
        good_left -= 1

    iterator = iter(picked)

    def repl(match: re.Match[str]) -> str:
        return f"[{match.group(1)}] = {next(iterator)}"

    return TUTOR_MOVE_ENTRY_PATTERN.sub(repl, text)


def _compat_probability(
    species: dict[str, object] | None,
    move: str,
    move_data: dict[str, dict[str, object]],
    prefer_same_type: bool,
) -> float:
    if not prefer_same_type or not species:
        return 0.5
    move_type = _move_type(move, move_data)
    types = set(species.get("types", ()))
    if move_type in types:
        return 0.9
    if move_type == "TYPE_NORMAL":
        return 0.5
    return 0.25


def randomize_tmhm_compatibility(
    text: str,
    tms_hms_text: str,
    species_info: dict[str, dict[str, object]],
    move_data: dict[str, dict[str, object]],
    *,
    prefer_same_type: bool,
) -> str:
    tm_ids, hm_ids = parse_tmhm_ids(tms_hms_text)
    fields = tm_ids + hm_ids

    def repl(match: re.Match[str]) -> str:
        species = match.group(1)
        if species == "SPECIES_NONE":
            return match.group(0)
        info = species_info.get(species, {"types": (), "attack": 50, "sp_attack": 50})
        learned = []
        for field in fields:
            move = f"MOVE_{field}"
            if random.random() < _compat_probability(info, move, move_data, prefer_same_type):
                learned.append(field)
        if not learned:
            return f"    [{species}] = {{ .learnset = {{\n    }} }},"
        lines = [f"    [{species}] = {{ .learnset = {{"]
        for field in learned:
            lines.append(f"        .{field} = TRUE,")
        lines.append("    } },")
        return "\n".join(lines)

    return TMHM_LEARNSET_BLOCK_PATTERN.sub(repl, text)


def remap_tmhm_compatibility_fields(
    text: str,
    old_tms_hms_text: str,
    new_tms_hms_text: str,
) -> str:
    old_tm_ids, old_hm_ids = parse_tmhm_ids(old_tms_hms_text)
    new_tm_ids, new_hm_ids = parse_tmhm_ids(new_tms_hms_text)
    field_map = {
        old: new
        for old, new in zip(old_tm_ids + old_hm_ids, new_tm_ids + new_hm_ids)
    }

    def repl(match: re.Match[str]) -> str:
        field = match.group(1)
        return f".{field_map.get(field, field)} = TRUE"

    return re.sub(r"\.([A-Z0-9_]+)\s*=\s*TRUE", repl, text)


def randomize_tutor_compatibility(
    text: str,
    species_info: dict[str, dict[str, object]],
    move_data: dict[str, dict[str, object]],
    *,
    prefer_same_type: bool,
) -> str:
    tutor_slots = parse_tutor_moves(text)

    def repl(match: re.Match[str]) -> str:
        species = match.group(1)
        if species == "SPECIES_NONE":
            return match.group(0)
        info = species_info.get(species, {"types": (), "attack": 50, "sp_attack": 50})
        learned: list[str] = []
        for slot, actual_move in tutor_slots:
            if random.random() < _compat_probability(info, actual_move, move_data, prefer_same_type):
                learned.append(slot.removeprefix("TUTOR_"))
        if not learned:
            return f"    [{species:<24}] = (0),"
        lines = [f"    [{species:<24}] = (TUTOR({learned[0]})"]
        for slot in learned[1:]:
            lines.append(f"                                | TUTOR({slot})")
        lines[-1] += "),"
        return "\n".join(lines)

    return TUTOR_LEARNSET_BLOCK_PATTERN.sub(repl, text)


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


def _compute_depths(
    mapping: dict[str, str], cycles: list[list[str]] | None = None
) -> dict[str, int]:
    """For every node, number of edges to the first cycle node it reaches.

    Cycle nodes have depth 0. Off-cycle nodes inherit depth(target)+1.
    Every node reaches a cycle in a finite functional graph, so this
    terminates for all inputs.
    """
    if cycles is None:
        cycles = _find_cycles(mapping)
    on_cycle = {n for c in cycles for n in c}
    depth: dict[str, int] = {n: 0 for n in on_cycle}
    # Iterative resolution: walk from each node until we hit an already
    # known depth, then back-fill the walked prefix.
    for start in mapping:
        if start in depth:
            continue
        path: list[str] = []
        cur: str | None = start
        while cur is not None and cur not in depth:
            path.append(cur)
            cur = mapping.get(cur)
        base = depth[cur] if cur is not None else 0
        for i, node in enumerate(reversed(path)):
            depth[node] = base + i + 1
    return depth


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
    mapping: dict[str, str],
    cycle: list[str],
    target_max: int | None,
    target_min: int | None = None,
) -> bool:
    """Rule 3: swap two edges inside one cycle to split it in two.

    Cycle n0 -> n1 -> ... -> n(L-1) -> n0. Picking edges n_i -> n_(i+1)
    and n_j -> n_(j+1) and swapping their targets gives two cycles of
    length k = j - i and L - k. Every node's in-degree is preserved.
    Disallows length-1 halves (self-loops are forbidden) and, when
    target_min is given, halves shorter than target_min.
    """
    L = len(cycle)
    lo = max(2, target_min if target_min is not None else 2)
    hi = L - lo
    if hi < lo:
        return False
    if target_max is not None:
        # Prefer splits keeping both halves within max_cycle_length.
        lo_pref = max(lo, L - target_max)
        hi_pref = min(hi, target_max)
        if lo_pref <= hi_pref:
            lo, hi = lo_pref, hi_pref
        # else leave lo..hi unchanged: subsequent iterations will trim.
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


def _rule_reduce_tree_depth(
    mapping: dict[str, str],
    all_species: list[str],
    max_depth: int,
    *,
    max_indegree: int | None = None,
) -> bool:
    """Rule 5: compact trees hanging off cycles.

    For a leaf L with depth K > D (where D = max_depth), walking D-1
    hops along the path from L lands on a node u with depth K-D+1.
    Redirect u to a cycle node: u's new depth becomes 1, so L's new
    depth becomes D. Everything above u on the path gets shortened
    accordingly; everything below u stays put because their paths no
    longer go through u.

    Picks the cycle target with the lowest in-degree (respecting
    max_indegree) to avoid pushing the heaviest cycle nodes over the
    cap. Returns False if we can't find a legal redirect; callers
    (the outer loop) then move on to other rules and may try again.
    """
    cycles = _find_cycles(mapping)
    if not cycles:
        return False
    depths = _compute_depths(mapping, cycles)
    max_d = max(depths.values(), default=0)
    if max_d <= max_depth:
        return False
    deepest = [n for n, d in depths.items() if d == max_d]
    L = random.choice(deepest)

    # Walk D-1 hops from L toward the cycle. The node we land on, u,
    # has depth K - (D-1) = K - D + 1, which is >= 1 since K > D.
    u = L
    for _ in range(max(0, max_depth - 1)):
        u = mapping[u]
    if depths[u] == 0:
        # Shouldn't happen: D-1 hops from a node at depth K can't reach
        # a cycle node unless K < D, but we've already bailed for that.
        return False

    cycle_nodes = [n for c in cycles for n in c]
    indeg = _compute_indegree(mapping)
    cap = max_indegree if max_indegree is not None else len(all_species)
    candidates = [n for n in cycle_nodes if n != u and indeg[n] < cap]
    if not candidates:
        candidates = [n for n in cycle_nodes if n != u]
    if not candidates:
        return False
    # Lowest-indegree cycle node, break ties randomly.
    min_indeg = min(indeg[n] for n in candidates)
    best = [n for n in candidates if indeg[n] == min_indeg]
    w = random.choice(best)
    mapping[u] = w
    return True


def _pick_constrained_mapping(
    all_species: list[str],
    *,
    max_indegree: int | None,
    max_cycle_length: int | None,
    min_cycles: int | None,
    min_cycle_length: int | None = None,
    max_avg_indegree: float | None = None,
    max_tree_depth: int | None = None,
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
      5. _rule_reduce_tree_depth: redirect a mid-chain tail node to a
         cycle node, compacting the chain above it. Used to enforce
         max_tree_depth (the longest chain from any leaf into its cycle).
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
    if max_tree_depth is not None and max_tree_depth < 1:
        raise RuntimeError(
            "max_tree_depth must be >= 1 (0 requires every species to be on a cycle)."
        )

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
                if _rule_split_cycle(
                    mapping, cyc,
                    target_max=max_cycle_length,
                    target_min=min_cycle_length,
                ):
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
            # A cycle is split-valid iff both halves can be at least
            # max(2, min_cycle_length) long.
            min_half = max(2, min_cycle_length or 2)
            splittable = [c for c in cycles if len(c) >= 2 * min_half]
            if splittable:
                # Prefer the smallest splittable cycle: splitting
                # short cycles first leaves the big ones intact as a
                # reservoir for further splits.
                cyc = min(splittable, key=len)
                if _rule_split_cycle(
                    mapping, cyc,
                    target_max=max_cycle_length,
                    target_min=min_cycle_length,
                ):
                    continue
            # No splittable cycle: grow one (the shortest, cheapest)
            # toward 2*min_half by splicing in a tail. The strategy
            # "absorb tails into a cycle, then halve" is the most
            # efficient way to raise the cycle count under a tight
            # max_cycle_length.
            growable = sorted(cycles, key=len)
            did = False
            for cyc in growable:
                if len(cyc) >= 2 * min_half:
                    continue  # already splittable; handled above
                if _rule_extend_cycle(mapping, cyc, all_species):
                    did = True
                    break
            if did:
                continue
            # No tails left. Merge two cycles, after which the result
            # may be splittable (and net cycle count stays the same,
            # but a subsequent split will lift it).
            if len(cycles) >= 2:
                sample = random.sample(cycles, 2)
                if _rule_merge_cycles(mapping, sample[0], sample[1]):
                    continue
            break

        # Rule 5: compact any tail subtree that violates max_tree_depth.
        # Applied after the cycle rules so we only touch off-cycle
        # edges once the cycle structure is close to satisfied.
        if max_tree_depth is not None:
            depths = _compute_depths(mapping, cycles)
            if max(depths.values(), default=0) > max_tree_depth:
                if _rule_reduce_tree_depth(
                    mapping, all_species, max_tree_depth,
                    max_indegree=max_indegree,
                ):
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
    if max_tree_depth is not None:
        depths = _compute_depths(mapping, cycles)
        worst = max(depths.values(), default=0)
        if worst > max_tree_depth:
            raise RuntimeError(
                f"Could not enforce max_tree_depth={max_tree_depth} "
                f"(deepest remaining chain = {worst})."
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
    max_tree_depth: int | None = None,
) -> None:
    if (
        max_indegree is None
        and max_cycle_length is None
        and min_cycles is None
        and min_cycle_length is None
        and max_avg_indegree is None
        and max_tree_depth is None
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
            max_tree_depth=max_tree_depth,
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
        "src/data/pokemon/level_up_learnsets.h",
        "src/data/pokemon/egg_moves.h",
        "src/data/pokemon/tmhm_learnsets.h",
        "src/data/pokemon/tutor_learnsets.h",
        "include/constants/tms_hms.h",
    )

    # Restore from templates in randomizer/.
    move_templates = randomizer_dir / "move_templates"
    template_map = {
        "src/data/wild_encounters.json": randomizer_dir / "wild_encounters.json",
        "src/starter_choose.c": randomizer_dir / "starter_choose.c",
        "src/data/trainer_parties.h": randomizer_dir / "trainer_parties.h",
        "src/data/trainers.h": randomizer_dir / "trainers.h",
        "src/data/pokemon/level_up_learnsets.h": move_templates / "level_up_learnsets.h",
        "src/data/pokemon/egg_moves.h": move_templates / "egg_moves.h",
        "src/data/pokemon/tmhm_learnsets.h": move_templates / "tmhm_learnsets.h",
        "src/data/pokemon/tutor_learnsets.h": move_templates / "tutor_learnsets.h",
        "include/constants/tms_hms.h": move_templates / "tms_hms.h",
    }

    for rel in targets:
        src = template_map.get(rel)
        if src is None or not src.exists():
            raise FileNotFoundError(f"No template available to restore {rel}: {src}")
        dst = repo_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text())


def write_run_metadata(randomizer_dir: Path, args: argparse.Namespace) -> None:
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "argv": sys.argv[1:],
        "options": vars(args),
    }
    (randomizer_dir / "last_randomizer_run.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


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
    parser.add_argument(
        "--seed",
        default=None,
        help="Seed for reproducible randomization. Same seed and options produce the same output.",
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
        "--wild-level",
        type=int,
        default=None,
        help=(
            "Set every wild encounter min_level/max_level to this fixed level. "
            "Overrides --level-percent and --wild-level-percent for wild encounters. "
            "Clamped to 1..100."
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
        "--trainer-level",
        type=int,
        default=None,
        help=(
            "Set every trainer party level (.lvl) to this fixed level. "
            "Overrides --level-percent and --trainer-level-percent for trainer parties. "
            "Clamped to 1..100."
        ),
    )
    parser.add_argument(
        "--randomize-level-up-moves",
        action="store_true",
        help="Randomize Pokémon level-up learnsets while preserving learn levels.",
    )
    parser.add_argument(
        "--randomize-egg-moves",
        action="store_true",
        help="Randomize egg move lists while preserving list sizes.",
    )
    parser.add_argument(
        "--randomize-tm-moves",
        action="store_true",
        help="Randomize TM move slots. HM move slots are preserved.",
    )
    parser.add_argument(
        "--randomize-tutor-moves",
        action="store_true",
        help="Randomize move tutor move slots, excluding current TM/HM moves.",
    )
    parser.add_argument(
        "--randomize-tmhm-compat",
        action="store_true",
        help="Randomize each species' TM/HM compatibility.",
    )
    parser.add_argument(
        "--randomize-tutor-compat",
        action="store_true",
        help="Randomize each species' move tutor compatibility.",
    )
    parser.add_argument(
        "--moves-prefer-same-type",
        action="store_true",
        help="Bias randomized moves and compatibility toward the Pokémon's type(s).",
    )
    parser.add_argument(
        "--moves-good-damaging-percent",
        type=int,
        default=0,
        help="Percent of randomized move slots that should prefer good damaging moves (0..100).",
    )
    parser.add_argument(
        "--moves-block-broken",
        action="store_true",
        help="Exclude potentially game-breaking moves from randomized move pools.",
    )
    parser.add_argument(
        "--guaranteed-starting-moves",
        type=int,
        default=0,
        help=(
            "For level-up learnsets, ensure at least this many level-1 slots before "
            "randomizing moves. Existing learn levels are otherwise preserved."
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
    parser.add_argument(
        "--evo-max-tree-depth",
        type=int,
        default=None,
        help=(
            "When generating hardcoded random evolutions, cap the longest chain "
            "from any leaf (in-degree 0 node) into its cycle. Cycle nodes have "
            "depth 0; a leaf that reaches a cycle in k hops has depth k."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    randomizer_dir = Path(__file__).resolve().parent
    repo_root = randomizer_dir.parent

    if args.seed is not None and args.seed != "":
        random.seed(args.seed)

    move_selected = (
        args.randomize_level_up_moves
        or args.randomize_egg_moves
        or args.randomize_tm_moves
        or args.randomize_tutor_moves
        or args.randomize_tmhm_compat
        or args.randomize_tutor_compat
    )
    selected_any = args.all or args.wild or args.starters or args.trainers or move_selected

    wild_level_percent = args.level_percent if args.wild_level_percent is None else args.wild_level_percent
    trainer_level_percent = (
        args.level_percent if args.trainer_level_percent is None else args.trainer_level_percent
    )
    wild_fixed_level = args.wild_level
    trainer_fixed_level = args.trainer_level
    has_wild_level_change = wild_level_percent != 0 or wild_fixed_level is not None
    has_trainer_level_change = trainer_level_percent != 0 or trainer_fixed_level is not None

    restore_originals(randomizer_dir, repo_root)
    write_run_metadata(randomizer_dir, args)

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
            max_tree_depth=args.evo_max_tree_depth,
        )
    else:
        # Always reset to the default zero mapping so a previous
        # --hardcoded-random-evos run doesn't leak its random evolutions
        # into subsequent vanilla builds.
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
        # Allow "restore + level changes" as a convenience mode (used by the GUI):
        # when no randomization targets are selected, apply only the requested
        # level edits on top of the restored (template) files.
        if not selected_any and (has_wild_level_change or has_trainer_level_change):
            if has_wild_level_change:
                encounters_path = repo_root / "src/data/wild_encounters.json"
                encounters = encounters_path.read_text()
                encounters = scale_wild_levels_json(
                    encounters,
                    wild_level_percent,
                    fixed_level=wild_fixed_level,
                )
                encounters_path.write_text(encounters)

            if has_trainer_level_change:
                parties_path = repo_root / "src/data/trainer_parties.h"
                parties = parties_path.read_text()
                parties = scale_trainer_party_levels(
                    parties,
                    trainer_level_percent,
                    fixed_level=trainer_fixed_level,
                )
                parties_path.write_text(parties)
            write_run_metadata(randomizer_dir, args)
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

        encounters = scale_wild_levels_json(
            encounters,
            wild_level_percent,
            fixed_level=wild_fixed_level,
        )
        (repo_root / "src/data/wild_encounters.json").write_text(encounters)

    if do_starters:
        starter_code = (randomizer_dir / "starter_choose.c").read_text()
        starter_code = randomize_species_in_text(starter_code, all_species, per_occurrence=args.per_occurrence)
        (repo_root / "src/starter_choose.c").write_text(starter_code)

    if do_trainers:
        trainer_parties = (randomizer_dir / "trainer_parties.h").read_text()
        trainer_parties = randomize_species_in_text(trainer_parties, all_species, per_occurrence=args.per_occurrence)
        trainer_parties = scale_trainer_party_levels(
            trainer_parties,
            trainer_level_percent,
            fixed_level=trainer_fixed_level,
        )
        trainer_parties = convert_custom_moves_trainer_parties_to_default_moves(trainer_parties)
        (repo_root / "src/data/trainer_parties.h").write_text(trainer_parties)

        # Trainer definitions (switch party flags/macros to match converted parties)
        trainers = (randomizer_dir / "trainers.h").read_text()
        trainers = convert_trainers_to_default_moves(trainers)
        (repo_root / "src/data/trainers.h").write_text(trainers)

    if move_selected:
        move_constants = (repo_root / "include/constants/moves.h").read_text()
        battle_moves_text = (repo_root / "src/data/battle_moves.h").read_text()
        species_info_text = (repo_root / "src/data/pokemon/species_info.h").read_text()
        all_moves = parse_move_constants(move_constants)
        move_data = parse_battle_moves(battle_moves_text)
        species_info = parse_species_info(species_info_text)

        tms_hms_path = repo_root / "include/constants/tms_hms.h"
        tms_hms_text = tms_hms_path.read_text()
        original_tms_hms_text = tms_hms_text

        hm_ids = parse_tmhm_ids(tms_hms_text)[1]
        levelup_excluded = {f"MOVE_{hm_id}" for hm_id in hm_ids}
        valid_levelup_moves = _valid_moves(
            all_moves,
            move_data,
            no_broken=args.moves_block_broken,
            excluded_moves=levelup_excluded,
        )
        good_damaging_percent = _clamp_percent(args.moves_good_damaging_percent)

        if args.randomize_tm_moves:
            tms_hms_text = randomize_tm_moves(
                tms_hms_text,
                all_moves,
                move_data,
                no_broken=args.moves_block_broken,
                good_damaging_percent=good_damaging_percent,
            )
            tms_hms_path.write_text(tms_hms_text)

        if args.randomize_level_up_moves:
            levelup_path = repo_root / "src/data/pokemon/level_up_learnsets.h"
            pointer_text = (repo_root / "src/data/pokemon/level_up_learnset_pointers.h").read_text()
            levelup_text = randomize_level_up_learnsets(
                levelup_path.read_text(),
                pointer_text,
                species_info,
                valid_levelup_moves,
                move_data,
                prefer_same_type=args.moves_prefer_same_type,
                good_damaging_percent=good_damaging_percent,
                guaranteed_starting_moves=max(0, args.guaranteed_starting_moves),
            )
            levelup_path.write_text(levelup_text)

        if args.randomize_egg_moves:
            egg_path = repo_root / "src/data/pokemon/egg_moves.h"
            egg_text = randomize_egg_moves(
                egg_path.read_text(),
                species_info,
                valid_levelup_moves,
                move_data,
                prefer_same_type=args.moves_prefer_same_type,
                good_damaging_percent=good_damaging_percent,
            )
            egg_path.write_text(egg_text)

        tutor_path = repo_root / "src/data/pokemon/tutor_learnsets.h"
        tutor_text = tutor_path.read_text()
        if args.randomize_tutor_moves:
            tutor_text = randomize_tutor_moves(
                tutor_text,
                all_moves,
                move_data,
                tms_hms_text,
                no_broken=args.moves_block_broken,
                good_damaging_percent=good_damaging_percent,
            )
            tutor_path.write_text(tutor_text)

        if args.randomize_tmhm_compat:
            tmhm_path = repo_root / "src/data/pokemon/tmhm_learnsets.h"
            tmhm_text = randomize_tmhm_compatibility(
                tmhm_path.read_text(),
                tms_hms_text,
                species_info,
                move_data,
                prefer_same_type=args.moves_prefer_same_type,
            )
            tmhm_path.write_text(tmhm_text)
        elif args.randomize_tm_moves:
            tmhm_path = repo_root / "src/data/pokemon/tmhm_learnsets.h"
            tmhm_text = remap_tmhm_compatibility_fields(
                tmhm_path.read_text(),
                original_tms_hms_text,
                tms_hms_text,
            )
            tmhm_path.write_text(tmhm_text)

        if args.randomize_tutor_compat:
            tutor_text = randomize_tutor_compatibility(
                tutor_text,
                species_info,
                move_data,
                prefer_same_type=args.moves_prefer_same_type,
            )
            tutor_path.write_text(tutor_text)

    write_run_metadata(randomizer_dir, args)


if __name__ == "__main__":
    main()
