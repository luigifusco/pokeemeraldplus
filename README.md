# Pokémon Emerald

This is a decompilation of Pokémon Emerald.

It builds the following ROM:

* [**pokeemerald.gba**](https://datomatic.no-intro.org/index.php?page=show_record&s=23&n=1961) `sha1: f3ae088181bf583e55daf962a92bb46f4f1d07b7`

To set up the repository, see [INSTALL.md](INSTALL.md).

## Emerald Forge

The repository ships **Emerald Forge**, a local browser studio for configuring
gameplay changes, generating remixed content, compiling the ROM, and inspecting
reports. To launch it:

```bash
# Create a virtual environment (recommended on Debian/Ubuntu/WSL).
python3 -m venv .venv
source .venv/bin/activate
pip install -r forge/requirements.txt
python3 -m forge
```

If you hit `error: externally-managed-environment`, that's PEP 668
refusing to touch the system Python. Use the `venv` recipe above, or
install per-user:

```bash
pip install --user -r forge/requirements.txt
python3 -m forge
```

This starts a local server on <http://127.0.0.1:8765/> and opens your
browser. Forge organizes configuration into seven workspaces:

* **Remix** — species targets, distribution models, seed, and level curve.
* **Moves & Evolutions** — learnsets, compatibility, evolution modes, and CP-SAT graph constraints.
* **Trainers** — randomized boss quality and curated opponent upgrades.
* **World** — HM progression, encounters, facilities, and starting state.
* **Battle** — battle format, EXP/economy rules, stat stages, and external control.
* **Experience** — movement, text, transitions, animation speed, and evolution pacing.
* **Build** — pipeline selection, live command preview, console, reports, and evolution graph.

Presets are stored in your browser's local storage (accessible via the
Presets button in the top bar).

Forge also keeps non-default settings in the browser URL. Changing a control
updates the URL without reloading the page; **Copy configuration URL** creates
a shareable link that restores configuration, pipeline options, and the active
workspace.

### CLI flags

```bash
python3 -m forge --host 127.0.0.1 --port 8765
python3 -m forge --no-browser   # don't auto-open a tab
python3 -m forge --reload       # dev mode
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
While the ROM is waiting for the remote opponent, hold **A+B+Start+Select** to
fall back to Emerald's default CPU choice for that decision.

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

You can also override the target at runtime from mGBA's Scripting console:

```lua
battleui.connect("luigifusco.dev", 9877, "shared-secret")
battleui.status()
battleui.disconnect()
```

Useful when you want to retarget without restarting mGBA, or when launching
mGBA from a desktop shortcut without env vars.

Your friend opens:

```
https://luigifusco.dev/?token=some-long-random-string
```

For a full public deployment walkthrough (systemd unit, nginx TLS config,
firewall, troubleshooting) see [`docs/battleui-remote.md`](docs/battleui-remote.md).
