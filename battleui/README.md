# battleui

Local Python server that brokers between the mGBA Lua bridge (TCP) and a
single-page browser UI (WebSocket). See the top-level README section "mGBA
web-UI opponent" for the full usage flow.

## Run

```
pip install -r battleui/requirements.txt
python -m battleui --http-port 8000 --tcp-port 8765
```

## Ports

- `127.0.0.1:8000`  HTTP + WebSocket (browser)
- `127.0.0.1:8765`  TCP, newline-delimited JSON (mGBA Lua bridge)

## Flow

1. Lua bridge connects to the TCP port and keeps the connection open.
2. ROM posts a decision request into the EWRAM mailbox; the Lua script reads
   it, sends `{"type":"request","seq":N,...}` over TCP.
3. Router forwards to the browser over WebSocket.
4. Browser submits `{"type":"response","seq":N,"action":..,"param1":..,"param2":..}`.
5. Router forwards back over TCP; Lua writes response bytes and flips the
   mailbox state so the ROM can resume.

## Tests

```
pytest battleui/tests/ -q
```
