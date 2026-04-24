# Pokémon Emerald

This is a decompilation of Pokémon Emerald.

It builds the following ROM:

* [**pokeemerald.gba**](https://datomatic.no-intro.org/index.php?page=show_record&s=23&n=1961) `sha1: f3ae088181bf583e55daf962a92bb46f4f1d07b7`

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
  watch the live command preview, then click Build and
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

## mGBA web-UI opponent

Drive the AI trainer's decisions from a browser tab while the ROM runs in a
single mGBA instance (replaces the old link-cable remote-opponent feature).

Build with the opt-in flag:

```
make WEBUI_OPPONENT=1 -j$(nproc)
```

Install deps + start the local broker (HTTP 9876, TCP 9877, both 127.0.0.1):

```
pip install -r battleui/requirements.txt
python -m battleui
```

Generate the mailbox address file so the Lua script can jump straight to the
struct (optional — the script also falls back to an EWRAM magic scan):

```
make WEBUI_OPPONENT=1 syms
awk '/gWebuiOpponentMailbox/ {print "0x"$1; exit}' pokeemerald.sym \
    > tools/battleui/mailbox_addr.txt
```

Load the ROM in mGBA (0.10+), open **Tools → Scripting…**, and load
`tools/battleui/mgba_bridge.lua`. Then open
[http://127.0.0.1:9876](http://127.0.0.1:9876). Start a trainer battle — the
page will prompt you to pick the opponent's move / switch / item on every turn.

Tests: `pytest battleui/tests/ -q`.

### Playing remotely via a relay server

Both the Lua bridge and the browser only need to reach the Python server over
the network, so you can host the server on a public box (e.g. `luigifusco.dev`)
and have you + a friend connect from different machines.

On the server:

```
# behind nginx/caddy terminating TLS on 443 -> proxy to 9876
export BATTLEUI_TOKEN="some-long-random-string"
python -m battleui --http-host 0.0.0.0 --tcp-host 0.0.0.0 --token "$BATTLEUI_TOKEN"
```

When binding publicly **always** set `--token` (or `$BATTLEUI_TOKEN`):

- TCP connections must send `{"type":"hello","token":"..."}` as their first
  line or they are dropped.
- WebSocket URLs must include `?token=...` or they are rejected.

On your (emulator) machine, point the Lua bridge at the server:

```
BATTLEUI_HOST=luigifusco.dev \
BATTLEUI_PORT=9877 \
BATTLEUI_TOKEN=some-long-random-string \
mgba pokeemerald.gba
```

(or edit the `HOST` / `PORT` / `TOKEN` defaults at the top of
`tools/battleui/mgba_bridge.lua`). Load the script from **Tools → Scripting…**.

Your friend opens:

```
https://luigifusco.dev/?token=some-long-random-string
```

For a full public deployment walkthrough (systemd unit, nginx TLS config,
firewall, troubleshooting) see [`docs/battleui-remote.md`](docs/battleui-remote.md).

