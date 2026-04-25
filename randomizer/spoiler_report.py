"""Generate an HTML spoiler report for the latest randomizer output."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path

import evolution_graph
import randomize


SPECIES_RE = randomize.RANDOMIZE_SPECIES_PATTERN


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def pretty_token(token: str) -> str:
    token = str(token)
    for prefix in ("SPECIES_", "MOVE_", "TYPE_", "TUTOR_MOVE_"):
        token = token.removeprefix(prefix)
    return token.replace("_", " ").title()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()


def load_metadata(randomizer_dir: Path) -> dict:
    path = randomizer_dir / "last_randomizer_run.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def section(title: str, body: str) -> str:
    return f"<section><h2>{esc(title)}</h2>{body}</section>"


def table(headers: list[str], rows: list[list[object]], *, empty: str = "No changes.") -> str:
    if not rows:
        return f"<p class=\"empty\">{esc(empty)}</p>"
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "\n".join(
        "<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def definition_list(items: list[tuple[str, object]]) -> str:
    rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in items)
    return f"<dl>{rows}</dl>"


def species_replacements(template_text: str, generated_text: str) -> list[list[object]]:
    old = SPECIES_RE.findall(template_text)
    new = SPECIES_RE.findall(generated_text)
    rows: list[list[object]] = []
    for i, (before, after) in enumerate(zip(old, new), start=1):
        if before != after:
            rows.append([i, pretty_token(before), pretty_token(after)])
    return rows


def wild_encounter_rows(template_text: str, generated_text: str) -> list[list[object]]:
    if not template_text or not generated_text:
        return []
    before = json.loads(template_text)
    after = json.loads(generated_text)
    rows: list[list[object]] = []
    for group_before, group_after in zip(
        before.get("wild_encounter_groups", []),
        after.get("wild_encounter_groups", []),
    ):
        for enc_before, enc_after in zip(
            group_before.get("encounters", []),
            group_after.get("encounters", []),
        ):
            map_name = enc_before.get("map", "?")
            for kind, data_before in enc_before.items():
                if not isinstance(data_before, dict) or "mons" not in data_before:
                    continue
                data_after = enc_after.get(kind, {})
                if not isinstance(data_after, dict):
                    continue
                for i, (mon_before, mon_after) in enumerate(
                    zip(data_before.get("mons", []), data_after.get("mons", [])),
                    start=1,
                ):
                    species_before = mon_before.get("species")
                    species_after = mon_after.get("species")
                    if species_before == species_after and mon_before == mon_after:
                        continue
                    before_levels = f"{mon_before.get('min_level', '?')}-{mon_before.get('max_level', '?')}"
                    after_levels = f"{mon_after.get('min_level', '?')}-{mon_after.get('max_level', '?')}"
                    rows.append([
                        map_name,
                        kind,
                        i,
                        pretty_token(species_before),
                        pretty_token(species_after),
                        before_levels,
                        after_levels,
                    ])
    return rows


def level_up_learnset_map(text: str, pointer_text: str) -> dict[str, list[tuple[int, str]]]:
    species_by_learnset = {
        learnset: species
        for species, learnset in randomize.LEVEL_UP_POINTER_PATTERN.findall(pointer_text)
        if species != "SPECIES_NONE"
    }
    result: dict[str, list[tuple[int, str]]] = {}
    for learnset, body in randomize.LEVEL_UP_BLOCK_PATTERN.findall(text):
        species = species_by_learnset.get(learnset)
        if species is None:
            continue
        result[species] = [
            (int(level), move)
            for level, move in randomize.LEVEL_UP_ENTRY_PATTERN.findall(body)
        ]
    return result


def level_up_rows(template_text: str, generated_text: str, pointer_text: str) -> list[list[object]]:
    before = level_up_learnset_map(template_text, pointer_text)
    after = level_up_learnset_map(generated_text, pointer_text)
    rows: list[list[object]] = []
    for species in sorted(set(before) | set(after)):
        old_entries = before.get(species, [])
        new_entries = after.get(species, [])
        if old_entries == new_entries:
            continue
        old_text = ", ".join(f"L{level} {pretty_token(move)}" for level, move in old_entries)
        new_text = ", ".join(f"L{level} {pretty_token(move)}" for level, move in new_entries)
        rows.append([pretty_token(species), old_text, new_text])
    return rows


def egg_move_map(text: str) -> dict[str, list[str]]:
    return {
        f"SPECIES_{species}": re.findall(r"MOVE_[A-Z0-9_]+", body)
        for species, body in randomize.EGG_MOVES_BLOCK_PATTERN.findall(text)
    }


def egg_move_rows(template_text: str, generated_text: str) -> list[list[object]]:
    before = egg_move_map(template_text)
    after = egg_move_map(generated_text)
    rows: list[list[object]] = []
    for species in sorted(set(before) | set(after)):
        old_moves = before.get(species, [])
        new_moves = after.get(species, [])
        if old_moves == new_moves:
            continue
        rows.append([
            pretty_token(species),
            ", ".join(pretty_token(move) for move in old_moves),
            ", ".join(pretty_token(move) for move in new_moves),
        ])
    return rows


def tm_rows(template_text: str, generated_text: str) -> list[list[object]]:
    old_tms, old_hms = randomize.parse_tmhm_ids(template_text)
    new_tms, new_hms = randomize.parse_tmhm_ids(generated_text)
    rows: list[list[object]] = []
    for i, (old, new) in enumerate(zip(old_tms, new_tms), start=1):
        if old != new:
            rows.append([f"TM{i:02d}", pretty_token(old), pretty_token(new)])
    for i, (old, new) in enumerate(zip(old_hms, new_hms), start=1):
        if old != new:
            rows.append([f"HM{i:02d}", pretty_token(old), pretty_token(new)])
    return rows


def tutor_rows(template_text: str, generated_text: str) -> list[list[object]]:
    before = randomize.parse_tutor_moves(template_text)
    after = randomize.parse_tutor_moves(generated_text)
    rows: list[list[object]] = []
    for (slot, old_move), (_, new_move) in zip(before, after):
        if old_move != new_move:
            rows.append([pretty_token(slot), pretty_token(old_move), pretty_token(new_move)])
    return rows


def compatibility_rows(template_text: str, generated_text: str, pattern) -> list[list[object]]:
    rows: list[list[object]] = []
    before = {species: set(re.findall(r"\.([A-Z0-9_]+)\s*=\s*TRUE|TUTOR\((MOVE_[A-Z0-9_]+)\)", body))
              for species, body in pattern.findall(template_text)}
    after = {species: set(re.findall(r"\.([A-Z0-9_]+)\s*=\s*TRUE|TUTOR\((MOVE_[A-Z0-9_]+)\)", body))
             for species, body in pattern.findall(generated_text)}
    for species in sorted(set(before) | set(after)):
        old_items = {a or b for a, b in before.get(species, set())}
        new_items = {a or b for a, b in after.get(species, set())}
        if old_items == new_items:
            continue
        added = sorted(new_items - old_items)
        removed = sorted(old_items - new_items)
        rows.append([
            pretty_token(species),
            len(old_items),
            len(new_items),
            ", ".join(pretty_token(item) for item in added[:12]),
            ", ".join(pretty_token(item) for item in removed[:12]),
        ])
    return rows


def evolution_rows(repo_root: Path) -> tuple[str, list[list[object]]]:
    header = repo_root / "src/data/random_evolutions.h"
    mapping = evolution_graph.parse_table(header) if header.exists() else {}
    rows = [
        [pretty_token(src), pretty_token(dst)]
        for src, dst in sorted(mapping.items())
    ]
    return ("Hardcoded random evolution mapping" if rows else "Hardcoded random evolution mapping"), rows


def ensure_evolution_graph(randomizer_dir: Path, repo_root: Path) -> str:
    header = repo_root / "src/data/random_evolutions.h"
    if not header.exists():
        return "random_evolutions.h does not exist yet."
    mapping = evolution_graph.parse_table(header)
    dot_path = randomizer_dir / "evolution_paths.dot"
    png_path = randomizer_dir / "evolution_paths.png"
    if mapping:
        dot_text, _ = evolution_graph.build_dot(mapping, engine="dot", only_reachable_from=None)
    else:
        dot_text = "\n".join([
            "digraph evolutions {",
            "    graph [bgcolor=white, rankdir=LR];",
            "    node [shape=box, style=\"rounded,filled\", fillcolor=\"#f7f7f7\", fontname=\"Helvetica\"];",
            "    empty [label=\"No hardcoded random evolutions generated\"];",
            "}",
            "",
        ])
    dot_path.write_text(dot_text)
    try:
        evolution_graph.render(dot_path, png_path, "png", "dot")
    except subprocess.CalledProcessError as exc:
        return f"Graphviz failed: {exc}"
    return "Graph image generated." if png_path.exists() else "Graphviz not found; DOT file generated."


def build_report(randomizer_dir: Path, repo_root: Path, out_path: Path) -> None:
    metadata = load_metadata(randomizer_dir)
    graph_status = ensure_evolution_graph(randomizer_dir, repo_root)
    move_templates = randomizer_dir / "move_templates"

    sections: list[str] = []
    options = metadata.get("options", {})
    enabled = sorted(k for k, v in options.items() if v is True)
    sections.append(section("Run", definition_list([
        ("Seed", metadata.get("seed") or "(none)"),
        ("Generated at", metadata.get("generated_at") or "(unknown)"),
        ("Enabled options", ", ".join(enabled) if enabled else "(none)"),
        ("Command", " ".join(metadata.get("argv", [])) or "(unknown)"),
    ])))

    graph_img = randomizer_dir / "evolution_paths.png"
    graph_body = f"<p>{esc(graph_status)}</p>"
    if graph_img.exists():
        graph_body += "<p><img class=\"graph\" src=\"/api/evolution-graph/image\" alt=\"Evolution graph\"></p>"
    graph_body += "<p><a href=\"/api/evolution-graph/dot\">Download Graphviz DOT</a></p>"
    sections.append(section("Evolution graph", graph_body))

    evo_title, evo_rows = evolution_rows(repo_root)
    sections.append(section(evo_title, table(["Species", "Evolves into"], evo_rows, empty="No hardcoded random evolution mapping.")))

    sections.append(section(
        "Starters",
        table(
            ["Slot", "Original", "Randomized"],
            species_replacements(read_text(randomizer_dir / "starter_choose.c"), read_text(repo_root / "src/starter_choose.c")),
            empty="Starter species unchanged.",
        ),
    ))
    sections.append(section(
        "Wild encounters",
        table(
            ["Map", "Encounter type", "Slot", "Original", "Randomized", "Old levels", "New levels"],
            wild_encounter_rows(read_text(randomizer_dir / "wild_encounters.json"), read_text(repo_root / "src/data/wild_encounters.json")),
            empty="Wild encounters unchanged.",
        ),
    ))
    sections.append(section(
        "Trainer parties",
        table(
            ["Slot", "Original", "Randomized"],
            species_replacements(read_text(randomizer_dir / "trainer_parties.h"), read_text(repo_root / "src/data/trainer_parties.h")),
            empty="Trainer party species unchanged.",
        ),
    ))

    pointer_text = read_text(repo_root / "src/data/pokemon/level_up_learnset_pointers.h")
    sections.append(section(
        "Level-up moves",
        table(
            ["Species", "Original", "Randomized"],
            level_up_rows(
                read_text(move_templates / "level_up_learnsets.h"),
                read_text(repo_root / "src/data/pokemon/level_up_learnsets.h"),
                pointer_text,
            ),
            empty="Level-up learnsets unchanged.",
        ),
    ))
    sections.append(section(
        "Egg moves",
        table(
            ["Species", "Original", "Randomized"],
            egg_move_rows(read_text(move_templates / "egg_moves.h"), read_text(repo_root / "src/data/pokemon/egg_moves.h")),
            empty="Egg moves unchanged.",
        ),
    ))
    sections.append(section(
        "TMs and HMs",
        table(
            ["Slot", "Original", "Randomized"],
            tm_rows(read_text(move_templates / "tms_hms.h"), read_text(repo_root / "include/constants/tms_hms.h")),
            empty="TM/HM moves unchanged.",
        ),
    ))
    sections.append(section(
        "Move tutors",
        table(
            ["Tutor slot", "Original", "Randomized"],
            tutor_rows(read_text(move_templates / "tutor_learnsets.h"), read_text(repo_root / "src/data/pokemon/tutor_learnsets.h")),
            empty="Tutor moves unchanged.",
        ),
    ))
    sections.append(section(
        "TM/HM compatibility",
        table(
            ["Species", "Old count", "New count", "Added", "Removed"],
            compatibility_rows(
                read_text(move_templates / "tmhm_learnsets.h"),
                read_text(repo_root / "src/data/pokemon/tmhm_learnsets.h"),
                randomize.TMHM_LEARNSET_BLOCK_PATTERN,
            ),
            empty="TM/HM compatibility unchanged.",
        ),
    ))
    sections.append(section(
        "Tutor compatibility",
        table(
            ["Species", "Old count", "New count", "Added", "Removed"],
            compatibility_rows(
                read_text(move_templates / "tutor_learnsets.h"),
                read_text(repo_root / "src/data/pokemon/tutor_learnsets.h"),
                randomize.TUTOR_LEARNSET_BLOCK_PATTERN,
            ),
            empty="Tutor compatibility unchanged.",
        ),
    ))

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pokeemeraldplus spoiler report</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, sans-serif; background: #101114; color: #eceff4; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ margin: 0 0 8px; }}
h2 {{ margin: 0 0 12px; }}
.subtitle, .empty {{ color: #a8b0bd; }}
section {{ margin-top: 24px; padding: 18px; background: #181a20; border: 1px solid #2c3038; border-radius: 10px; }}
dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; }}
dt {{ color: #a8b0bd; }}
dd {{ margin: 0; word-break: break-word; }}
.table-wrap {{ max-height: 520px; overflow: auto; border: 1px solid #2c3038; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 7px 10px; border-bottom: 1px solid #2c3038; text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; background: #20232b; z-index: 1; }}
tr:nth-child(even) td {{ background: #15171d; }}
.graph {{ max-width: 100%; background: white; border-radius: 8px; }}
a {{ color: #8fb4ff; }}
</style>
</head>
<body>
<main>
<h1>pokeemeraldplus spoiler report</h1>
<p class="subtitle">Generated from the current randomized source files.</p>
{''.join(sections)}
</main>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Output HTML path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    randomizer_dir = Path(__file__).resolve().parent
    repo_root = randomizer_dir.parent
    out_path = args.out or (randomizer_dir / "spoiler_report.html")
    build_report(randomizer_dir, repo_root, out_path)
    print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
