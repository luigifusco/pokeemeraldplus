# Pokémon Emerald

This is a decompilation of Pokémon Emerald.

It builds the following ROM:

* [**pokeemerald.gba**](https://datomatic.no-intro.org/index.php?page=show_record&s=23&n=1961) `sha1: f3ae088181bf583e55daf962a92bb46f4f1d07b7`

## Remote opponent builds (leader/follower)

These optional build variants are intended for emulator multiplayer-window setups.

Build the leader ROM:

* `make REMOTE_OPPONENT_LEADER=1 -j$(nproc)`
	* Outputs `pokeemerald.gba` by default

Build the follower ROM:

* `make REMOTE_OPPONENT_FOLLOWER=1 -j$(nproc)`
	* Outputs `follower.gba` by default

Optional output name overrides:

* `make ROM_NAME_OVERRIDE=myrom.gba`
* `make REMOTE_OPPONENT_LEADER=1 ROM_NAME_OVERRIDE=my_leader.gba`
* `make REMOTE_OPPONENT_FOLLOWER=1 ROM_NAME_OVERRIDE=my_follower.gba`

To set up the repository, see [INSTALL.md](INSTALL.md).

## Randomizer & Web UI

The repository ships a randomizer plus a browser-based UI that wraps
both the randomizer and `make`. To launch it:

```bash
# Create a virtual environment (recommended on Debian/Ubuntu/WSL).
python3 -m venv .venv
source .venv/bin/activate
pip install -r randomizer/requirements.txt
python3 -m randomizer.webui
```

If you hit `error: externally-managed-environment`, that's PEP 668
refusing to touch the system Python. Use the `venv` recipe above, or
install per-user:

```bash
pip install --user -r randomizer/requirements.txt
python3 -m randomizer.webui
```

This starts a local server on <http://127.0.0.1:8765/> and opens your
browser. The UI has five sections:

* **Randomizer** — pick targets (wild / starters / trainers),
  distribution (global / per-occurrence / per-map-consistent), and
  level scaling.
* **Evolutions** — vanilla, re-roll-each-time, or hardcoded-random
  (deterministic). Hardcoded mode exposes graph constraints
  (max in-degree, max/min cycle length, min cycles, max avg
  in-degree). A **Render graph** button visualizes the resulting
  evolution graph.
* **Gameplay** — EXP rules, economy tweaks, stat-stage modifiers,
  and walk-through-walls.
* **QoL & Speed** — instant text, fast animations, skip transitions,
  configurable wait-time divisor.
* **Build & Run** — toggle which steps to run, set `-j` parallelism,
  turn on `REMOTE_OPPONENT_LEADER` and optionally build the follower
  ROM too, watch the live command preview, then click Build and
  stream logs in real time.

Presets are stored in your browser's local storage (accessible via the
Presets button in the top bar).

### CLI flags

```bash
python3 -m randomizer.webui --host 127.0.0.1 --port 8765
python3 -m randomizer.webui --no-browser   # don't auto-open a tab
python3 -m randomizer.webui --reload       # dev mode
```

For contacts and other pret projects, see [pret.github.io](https://pret.github.io/).
