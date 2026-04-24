"""Extract human-readable species and move names from the decomp sources.

Parses `include/constants/species.h` + `src/data/text/species_names.h` and the
analogous files for moves at runtime. Results are cached in memory.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parent.parent

_DEFINE_RE = re.compile(r"^\s*#define\s+([A-Z0-9_]+)\s+(\(?[^/\n]+?)\s*(?://.*)?$")
_ENTRY_RE = re.compile(r"\[\s*([A-Z0-9_]+)\s*\]\s*=\s*_\(\s*\"([^\"]*)\"\s*\)")


def _parse_defines(path: Path, prefix: str) -> Dict[str, int]:
    """Very small `#define NAME VALUE` evaluator.

    Only handles integer literals (decimal, hex) and references to previously
    defined symbols with the same prefix, which is enough for species / move
    constants. Unknown expressions are skipped silently.
    """
    out: Dict[str, int] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _DEFINE_RE.match(line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2).strip()
        if not name.startswith(prefix):
            continue
        # Strip surrounding parens.
        while expr.startswith("(") and expr.endswith(")"):
            expr = expr[1:-1].strip()
        val = _eval(expr, out)
        if val is not None:
            out[name] = val
    return out


def _eval(expr: str, defines: Dict[str, int]) -> int | None:
    expr = expr.strip()
    # Integer literal.
    try:
        return int(expr, 0)
    except ValueError:
        pass
    # Identifier.
    if expr in defines:
        return defines[expr]
    # Simple "A + N" / "A - N".
    for op in ("+", "-"):
        if op in expr:
            a, b = expr.rsplit(op, 1)
            va, vb = _eval(a, defines), _eval(b, defines)
            if va is not None and vb is not None:
                return va + vb if op == "+" else va - vb
    return None


def _parse_names(data_path: Path, defines: Dict[str, int]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    if not data_path.is_file():
        return out
    text = data_path.read_text(encoding="utf-8", errors="replace")
    for m in _ENTRY_RE.finditer(text):
        name, value = m.group(1), m.group(2)
        idx = defines.get(name)
        if idx is not None:
            out[idx] = value
    return out


_CACHE: Dict[str, Dict[int, str]] | None = None


def get_names() -> Dict[str, Dict[int, str]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    species_defs = _parse_defines(REPO_ROOT / "include/constants/species.h", "SPECIES_")
    move_defs = _parse_defines(REPO_ROOT / "include/constants/moves.h", "MOVE_")
    _CACHE = {
        "species": _parse_names(REPO_ROOT / "src/data/text/species_names.h", species_defs),
        "moves": _parse_names(REPO_ROOT / "src/data/text/move_names.h", move_defs),
    }
    return _CACHE
