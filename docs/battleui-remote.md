# battleui — remote relay deployment

This document is a self-contained spec for deploying the **battleui** relay
server on a public host (example: `luigifusco.dev`) so that the game owner and
a remote friend can share an opponent-control session over the internet.

It is intended to be read and acted on by an AI assistant or ops engineer who
does **not** already know the project.

---

## 1. What battleui is

battleui lets a human choose the AI opponent's battle decisions in a
`pokeemeraldplus` ROM running under mGBA. There is no multi-ROM link-cable
simulation: only the ROM owner's mGBA runs the game. The "opponent brain"
lives in a browser tab that can be anywhere on the internet.

Components:

| Component | Runs on | Role |
|-----------|---------|------|
| ROM built with `WEBUI_OPPONENT=1` | player's PC, inside mGBA | Writes a 260-byte request mailbox in EWRAM whenever the opponent AI needs to make a decision, then spins a wait-handler until a response appears in the same mailbox. |
| `tools/battleui/mgba_bridge.lua` | player's mGBA (Tools → Scripting) | Polls the mailbox each frame. On request, sends a JSON line over TCP. On response-from-server, writes the decision back into the mailbox. |
| `battleui` Python server (this doc) | public server (e.g. `luigifusco.dev`) | Relays between the Lua TCP client and the browser WebSocket. Also serves the static SPA and a `/names.json` endpoint with species/move names parsed from the decomp sources. |
| Browser SPA | friend's browser | Renders the battle state (mon sprites, HP, moves, party, items) and lets the user submit a decision over WebSocket. |

Core design constraints:

- The Lua side **cannot do TLS** (mGBA's Lua sandbox has no SSL). It speaks
  plain TCP, one JSON object per line (`\n`-delimited NDJSON).
- The browser uses WebSocket, which can be TLS-wrapped (`wss://`) when served
  behind a reverse proxy.
- Authentication is a single **shared secret token** (`BATTLEUI_TOKEN`). The
  server rejects TCP clients that don't send a hello frame with the token
  and rejects WebSockets that don't include `?token=…`. There is no per-user
  auth, no sessions, no registration.

---

## 2. Network topology to deploy

Target layout on `luigifusco.dev`:

```
                         ┌────────────────────────── luigifusco.dev ───────────────────────────┐
                         │                                                                     │
  ROM + mGBA + Lua ──────┼──▶ TCP :9877 ──────┐                                                │
  (outbound, plain TCP)  │                    │                                                │
                         │                    ▼                                                │
                         │            ┌────────────────┐                                       │
                         │            │ battleui       │ /ws (WebSocket)                       │
                         │            │ python server  │ ◀──── nginx (TLS, :443) ◀── internet  │
                         │            │                │ /,/names.json,/static/*               │
                         │            └────────────────┘                                       │
                         │                                                                     │
                         └─────────────────────────────────────────────────────────────────────┘
```

Two listen sockets on the battleui process:

1. `HTTP :9876` (loopback from nginx) — FastAPI/uvicorn app: `/`, `/ws`,
   `/names.json`, `/static/…`.
2. `TCP :9877` (**bound publicly**) — NDJSON bridge for the Lua client.

The TCP bridge is **not** proxied through nginx: it's a line-oriented custom
protocol, not HTTP. The only port that needs to be reachable from the public
internet is therefore:

- `443/tcp` (nginx → uvicorn :9876)
- `9877/tcp` (direct to uvicorn's internal TCP server)

The public `:80/tcp` should redirect to `:443/tcp` (standard).

---

## 3. Required files already in the repo

Do not re-implement these — they exist. Relevant paths:

- `battleui/__init__.py`
- `battleui/__main__.py` — CLI entrypoint (`python -m battleui`). Flags:
  `--http-host`, `--http-port` (default 9876), `--tcp-host`,
  `--tcp-port` (default 9877), `--token` (also `$BATTLEUI_TOKEN`).
- `battleui/server.py` — FastAPI app + async TCP listener.
- `battleui/router.py` — in-memory broker between TCP client and WebSocket
  clients.
- `battleui/names.py` — parses `include/constants/{species,moves}.h` and
  `src/data/text/{species,move}_names.h`; cached on first request.
- `battleui/static/{index.html,app.js,style.css}` — SPA.
- `battleui/requirements.txt` — `fastapi`, `uvicorn[standard]`, `pytest`,
  `pytest-asyncio`, `httpx`.
- `battleui/tests/` — pytest suite (`pytest battleui/tests/ -q`).
- `tools/battleui/mgba_bridge.lua` — Lua client. Reads `BATTLEUI_HOST`,
  `BATTLEUI_PORT`, `BATTLEUI_TOKEN` from env (or falls back to the defaults
  hard-coded at the top of the file).
- `include/webui_opponent.h` + `src/webui_opponent.c` + hooks in
  `src/battle_controller_opponent.c`. Guarded by `#ifdef WEBUI_OPPONENT`.
- `Makefile` — opt-in flag `WEBUI_OPPONENT=1` changes the object dir to
  `build/emerald_webui/` and skips the `compare` target.

This doc does **not** cover building the ROM. Assume the player already has a
built `pokeemerald.gba` (see top-level README's "mGBA web-UI opponent" section).

---

## 4. Server setup on `luigifusco.dev`

### 4.1 System prerequisites

- Linux with systemd (Debian/Ubuntu assumed).
- Python 3.10+ (FastAPI and `asyncio.TaskGroup` features; 3.12 tested).
- `nginx` (or `caddy` — see §4.5 alt).
- TLS certificate for `luigifusco.dev` (Let's Encrypt via certbot works).
- Open TCP ports on the firewall: **80, 443, 9877**.
- A user to run the service, e.g. `battleui:battleui`.

### 4.2 Clone & install

```bash
sudo useradd -r -m -d /opt/battleui -s /usr/sbin/nologin battleui
sudo -u battleui git clone https://github.com/luigifusco/pokeemeraldplus.git /opt/battleui/app
sudo -u battleui python3 -m venv /opt/battleui/venv
sudo -u battleui /opt/battleui/venv/bin/pip install -r /opt/battleui/app/battleui/requirements.txt
```

Only the `battleui/` Python package and a few `include/`/`src/data/text/` files
are actually needed at runtime (names.py parses them), but cloning the whole
repo is easiest.

### 4.3 Generate a shared token

```bash
openssl rand -hex 24 | sudo tee /etc/battleui.token
sudo chown root:battleui /etc/battleui.token
sudo chmod 640 /etc/battleui.token
```

Share the resulting string privately with the player (for the Lua env var) and
the friend (as the URL query-string token).

### 4.4 systemd unit

Create `/etc/systemd/system/battleui.service`:

```ini
[Unit]
Description=battleui relay (pokeemeraldplus)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=battleui
Group=battleui
WorkingDirectory=/opt/battleui/app
EnvironmentFile=/etc/battleui.env
ExecStart=/opt/battleui/venv/bin/python -m battleui \
    --http-host 127.0.0.1 --http-port 9876 \
    --tcp-host 0.0.0.0   --tcp-port 9877
Restart=on-failure
RestartSec=2
# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/battleui/app
# The token file is root-owned 640, readable by the group only.
LoadCredential=token:/etc/battleui.token

[Install]
WantedBy=multi-user.target
```

Create `/etc/battleui.env`:

```bash
BATTLEUI_TOKEN=__REPLACE_WITH_CONTENTS_OF_/etc/battleui.token__
```

(The `LoadCredential` line above is optional — if you prefer systemd
credentials, wrap the ExecStart in a shell that reads
`$CREDENTIALS_DIRECTORY/token` and passes it as `--token`. The simpler
`EnvironmentFile` path is fine for a single-tenant box.)

Start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now battleui.service
systemctl status battleui.service
journalctl -u battleui.service -f
```

Verify:

```bash
curl -sS http://127.0.0.1:9876/names.json | head -c 100
# should return JSON with "species" and "moves" keys.
```

### 4.5 nginx reverse proxy

`/etc/nginx/sites-available/battleui.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name luigifusco.dev;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name luigifusco.dev;

    ssl_certificate     /etc/letsencrypt/live/luigifusco.dev/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/luigifusco.dev/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;

    # Static SPA, /names.json, REST endpoints.
    location / {
        proxy_pass http://127.0.0.1:9876;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For  $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSocket: needs Upgrade/Connection headers + long read timeout.
    location /ws {
        proxy_pass http://127.0.0.1:9876;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Enable + reload:

```bash
sudo ln -s /etc/nginx/sites-available/battleui.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Alternative with Caddy (`/etc/caddy/Caddyfile`):

```caddy
luigifusco.dev {
    reverse_proxy 127.0.0.1:9876
}
```

Caddy handles TLS + WebSocket upgrades automatically.

### 4.6 Firewall

The Lua bridge dials `luigifusco.dev:9877` directly (no HTTP/TLS).

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 9877/tcp
```

If you want to lock the bridge port to the player's IP, replace with:

```bash
sudo ufw allow from <player-public-ip>/32 to any port 9877 proto tcp
```

The token is still the mandatory authentication either way.

---

## 5. Player-side setup (reference, not to do on the server)

For completeness — the player runs:

```bash
BATTLEUI_HOST=luigifusco.dev \
BATTLEUI_PORT=9877 \
BATTLEUI_TOKEN=<shared token> \
mgba pokeemerald.gba
```

In mGBA: **Tools → Scripting… → Load** `tools/battleui/mgba_bridge.lua`. The
script logs `connected to luigifusco.dev:9877` once the TCP handshake + token
hello succeed.

The friend opens:

```
https://luigifusco.dev/?token=<shared token>
```

---

## 6. Protocol reference

### 6.1 TCP (Lua ↔ server), port 9877

- Framing: UTF-8 NDJSON, one JSON object per line, `\n` terminator.
- Server drops the connection if the first frame isn't a valid hello within
  5 seconds.

Lua → server:

```json
{"type":"hello","token":"…"}              ← first frame, when token enabled
{"type":"request","seq":N, "battlerId":…, "moveInfo":…, "partyInfo":…,
 "controlledMon":…, "targetMonLeft":…, "targetMonRight":…,
 "targetBattlerLeft":…, "targetBattlerRight":…, "trainerItems":[…]}
{"type":"heartbeat"}                      ← every ~1 s when idle
```

Server → Lua:

```json
{"type":"response","seq":N,"action":0|1|2|3,"param1":…,"param2":…}
```

`action` enum (matches `include/webui_opponent.h`):

| Value | Meaning |
|-------|---------|
| 0 | `WEBUI_OPP_ACTION_FIGHT` — param1 = move slot, param2 = target battler id |
| 1 | `WEBUI_OPP_ACTION_SWITCH` — param1 = party slot |
| 2 | `WEBUI_OPP_ACTION_USE_ITEM` — param1 = item slot |
| 3 | `WEBUI_OPP_ACTION_CANCEL_PARTNER` — doubles only |

Notes:

- `seq` is a monotonically increasing u8 owned by the ROM. The server must
  echo it unchanged; the router drops late responses.
- `nickname` inside `controlledMon` / `targetMon*` / `partyInfo.mons[]` is a
  **byte array** (GBA charmap), not a UTF-8 string.
- `moveInfo` with all-zero `moves[]` means the ROM is in `ChooseAction` stage
  (pick FIGHT vs SWITCH vs ITEM); a second request with populated moves
  follows if the user chose FIGHT.

### 6.2 WebSocket (browser ↔ server), `/ws`

Connection URL: `wss://luigifusco.dev/ws?token=<shared-token>`.

Server → browser:

```json
{"type":"hello"}                          ← sent on connect if no pending request
{"type":"request", …}                     ← forwarded TCP request
{"type":"heartbeat"}                      ← forwarded while idle
```

Browser → server:

```json
{"type":"response","seq":N,"action":…,"param1":…,"param2":…}
```

The server validates that `seq` matches the current pending request before
forwarding to the TCP side.

### 6.3 HTTP

- `GET /` — static `index.html`.
- `GET /static/…` — SPA assets.
- `GET /names.json` — cached `{"species": {id: name}, "moves": {id: name}}`
  dict parsed once from the decomp source tree.

---

## 7. Operations

### 7.1 Health checks

```bash
# Process
systemctl is-active battleui.service

# HTTP
curl -fsS https://luigifusco.dev/names.json | jq '.species | length'

# TCP (should just accept + wait for hello; close cleanly on Ctrl-C)
nc -v luigifusco.dev 9877
```

### 7.2 Logs

```bash
journalctl -u battleui.service -n 200 --no-pager
sudo tail -f /var/log/nginx/{access,error}.log
```

The battleui process logs:

- `TCP listener on 0.0.0.0:9877 (auth=on)` at startup.
- `tcp client connected: (ip, port)` / `…failed auth` / `…disconnected`.
- `ws error: …` for unexpected WebSocket exceptions.

### 7.3 Upgrades

```bash
sudo -u battleui git -C /opt/battleui/app pull
sudo -u battleui /opt/battleui/venv/bin/pip install -r /opt/battleui/app/battleui/requirements.txt
sudo systemctl restart battleui.service
```

### 7.4 Rotating the token

1. `openssl rand -hex 24 | sudo tee /etc/battleui.token`
2. Update `/etc/battleui.env` with the new value.
3. `sudo systemctl restart battleui.service`.
4. Send the new token to both player and friend.

### 7.5 Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Lua logs `connect failed` | firewall blocks 9877, or wrong `BATTLEUI_HOST`. |
| Lua logs `connected` but browser shows "waiting for emulator" forever | Lua token mismatch → server drops TCP silently after 5 s. Check server log for `failed auth`. |
| Browser gets `1008 policy violation` immediately | `?token=` missing or wrong. |
| WS disconnects every ~60 s | nginx `proxy_read_timeout` too low (default 60 s). Bump to ≥ 1 h as shown in §4.5. |
| SPA shows `#N` / `Move N` instead of names | `names.json` failed — the decomp source files were not included in the deployment. Copy `include/constants/{species,moves}.h` and `src/data/text/{species,move}_names.h` next to the battleui package, or clone the whole repo as in §4.2. |
| Continuous connect/disconnect loop on Lua side | Usually a crash in the Python process; check `journalctl -u battleui.service`. |

---

## 8. Security notes

- The shared token is the **only** auth boundary on both sockets. Treat it as
  a password: transmit out-of-band (Signal/email/etc.), never commit it,
  rotate if leaked.
- TCP :9877 is **plaintext**. An on-path attacker can see battle state and
  token. If this matters, either tunnel the Lua TCP through SSH/WireGuard
  (see `README.md`'s discussion), or restrict port 9877 to the player's IP
  via the firewall.
- The HTTP/WS side is TLS-terminated by nginx, so the friend's traffic is
  encrypted.
- There is no rate limiting. If the public IP is known to bad actors, put a
  `limit_req_zone` in nginx or restrict via `allow/deny`.
- No stored state: the server has nothing to back up. Everything is in-memory
  and reset on restart.

---

## 9. Out of scope for this doc

- Building the ROM (`make WEBUI_OPPONENT=1 …`) — see top-level `README.md`.
- Running mGBA and the Lua script — see top-level `README.md`.
- Local / single-machine deployment — see top-level `README.md` section
  "mGBA web-UI opponent".
- Replacing the TCP bridge with a TLS-capable transport — explicitly declined
  as a design choice; mGBA's Lua has no TLS.
