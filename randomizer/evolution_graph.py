"""Render the hardcoded random evolution table as a graph image.

Reads src/data/random_evolutions.h and produces:
  - randomizer/evolution_paths.dot (always)
  - randomizer/evolution_paths.<format> (if graphviz 'dot' is on PATH)

The hardcoded evolution mapping is a functional graph (each species has
exactly one outgoing edge). The resulting picture therefore shows trees
of pre-evolutions feeding into terminal cycles (fixed points included).

Usage:
    python3 randomizer/evolution_graph.py                 # default PNG
    python3 randomizer/evolution_graph.py --format svg
    python3 randomizer/evolution_graph.py --engine sfdp   # better for large graphs
    python3 randomizer/evolution_graph.py --only-reachable SPECIES_BULBASAUR
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


ENTRY_PATTERN = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*(SPECIES_[A-Z0-9_]+)\s*,")


def parse_table(header_path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for match in ENTRY_PATTERN.finditer(header_path.read_text()):
        mapping[match.group(1)] = match.group(2)
    return mapping


def pretty_name(species: str) -> str:
    # SPECIES_MR_MIME -> Mr Mime
    name = species.removeprefix("SPECIES_").replace("_", " ")
    return name.title()


def find_cycle_nodes(mapping: dict[str, str]) -> set[str]:
    """Return the set of nodes that lie on a cycle in the functional graph."""
    cycle_nodes: set[str] = set()
    state: dict[str, int] = {}  # 0 unseen, 1 on current walk, 2 done
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
            cycle_nodes.update(path[pos[node]:])
        for n in path:
            state[n] = 2
    return cycle_nodes


def build_dot(
    mapping: dict[str, str],
    *,
    engine: str,
    only_reachable_from: str | None,
) -> tuple[str, int]:
    edges = mapping
    if only_reachable_from is not None:
        seen: set[str] = set()
        stack = [only_reachable_from]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            if n in mapping:
                stack.append(mapping[n])
        edges = {src: dst for src, dst in mapping.items() if src in seen}

    cycle_nodes = find_cycle_nodes(mapping)

    lines: list[str] = []
    lines.append(f"digraph evolutions {{")
    lines.append(f"    layout={engine};")
    lines.append("    graph [bgcolor=white, overlap=false, splines=true, rankdir=LR];")
    lines.append("    node  [shape=box, style=\"rounded,filled\", fillcolor=\"#f7f7f7\", "
                 "fontname=\"Helvetica\", fontsize=10];")
    lines.append("    edge  [arrowsize=0.6, color=\"#555555\"];")

    nodes: set[str] = set()
    for src, dst in edges.items():
        nodes.add(src)
        nodes.add(dst)

    for n in sorted(nodes):
        if n in cycle_nodes:
            lines.append(
                f'    "{n}" [label="{pretty_name(n)}", '
                f'fillcolor="#ffd9d9", color="#c0392b", penwidth=2];'
            )
        else:
            lines.append(f'    "{n}" [label="{pretty_name(n)}"];')

    for src, dst in sorted(edges.items()):
        # An edge belongs to a cycle iff its source is a cycle node
        # (functional graph: cycle node's successor is also a cycle node).
        if src in cycle_nodes and dst in cycle_nodes:
            lines.append(f'    "{src}" -> "{dst}" [color="#c0392b", penwidth=2];')
        else:
            lines.append(f'    "{src}" -> "{dst}";')

    lines.append("}")
    lines.append("")
    return "\n".join(lines), len(edges)


def render(dot_path: Path, out_path: Path, fmt: str, engine: str) -> None:
    dot_bin = shutil.which("dot")
    if dot_bin is None:
        print("[warn] graphviz 'dot' not found on PATH; only the .dot file was written.",
              file=sys.stderr)
        return
    engine_bin = shutil.which(engine) or dot_bin
    subprocess.run(
        [engine_bin, f"-T{fmt}", str(dot_path), "-o", str(out_path)],
        check=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--header", type=Path,
                        default=None,
                        help="Path to random_evolutions.h (default: repo's src/data/random_evolutions.h).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output image path (default: randomizer/evolution_paths.<format>).")
    parser.add_argument("--format", default="png",
                        help="Output image format passed to graphviz (png, svg, pdf, ...).")
    parser.add_argument("--engine", default="dot",
                        choices=("dot", "neato", "fdp", "sfdp", "twopi", "circo"),
                        help="Graphviz layout engine (default: dot).")
    parser.add_argument("--only-reachable", default=None,
                        help="If set (e.g. SPECIES_BULBASAUR), only draw nodes reachable from this species.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    randomizer_dir = Path(__file__).resolve().parent
    repo_root = randomizer_dir.parent

    header_path = args.header or (repo_root / "src/data/random_evolutions.h")
    if not header_path.exists():
        print(f"[error] {header_path} not found. Run randomize.py --hardcoded-random-evos first.",
              file=sys.stderr)
        return 1

    mapping = parse_table(header_path)
    if not mapping:
        print(f"[error] no [SPECIES_*] = SPECIES_* entries found in {header_path}.", file=sys.stderr)
        return 1

    dot_text, edge_count = build_dot(mapping, engine=args.engine, only_reachable_from=args.only_reachable)
    dot_path = randomizer_dir / "evolution_paths.dot"
    dot_path.write_text(dot_text)
    print(f"[ok] wrote {dot_path} ({edge_count} edges)")

    out_path = args.out or (randomizer_dir / f"evolution_paths.{args.format}")
    try:
        render(dot_path, out_path, args.format, args.engine)
    except subprocess.CalledProcessError as exc:
        print(f"[error] graphviz failed: {exc}", file=sys.stderr)
        return 1
    if out_path.exists():
        print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
