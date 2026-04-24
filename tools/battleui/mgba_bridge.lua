--[[
mGBA Lua bridge for WEBUI_OPPONENT.

Purpose:
  Polls the EWRAM mailbox owned by pokeemerald (built with
  `make WEBUI_OPPONENT=1`), forwards "battle decision" requests to the local
  battleui Python server over TCP, and writes responses back so the ROM can
  resume. One frame callback; one mailbox; one TCP connection.

How to load (mGBA 0.10+):
  1. Start the ROM in mGBA.
  2. Tools -> Scripting...
  3. File -> Load script -> pick this file.
  Console output (connect/disconnect/errors) is printed to the Scripting log.

Required build:
  make WEBUI_OPPONENT=1 -j$(nproc)
  (Optional) Generate tools/battleui/mailbox_addr.txt via the helper documented
  in the README; if missing, this script falls back to scanning EWRAM for the
  magic sentinel.

Mailbox layout (bytes, little-endian, agbcc natural alignment).
Total size: 260 bytes. Confirm with `pokeemerald.map` if the symbol layout
changes. POKEMON_NAME_LENGTH=10 (nickname is 11 bytes incl. terminator),
MAX_MON_MOVES=4, PARTY_SIZE=6, MAX_TRAINER_ITEMS=4.

  WebuiOppMonInfo  (24 bytes, align=4):
    0  u16 species
    2  u16 hp
    4  u16 maxHp
    6  (pad 2)
    8  u32 status1
    12 u8  level
    13 u8  nickname[11]

  WebuiOppMoveInfo (18 bytes, align=2):
    0  u16 moves[4]     (bytes 0..7)
    8  u8  currentPp[4] (bytes 8..11)
    12 u8  maxPp[4]     (bytes 12..15)
    16 u8  monTypes[2]  (bytes 16..17)

  WebuiOppPartyInfo (148 bytes, align=4):
    0  u8 firstMonId
    1  u8 lastMonId
    2  u8 currentMonId
    3  u8 partnerMonId
    4  WebuiOppMonInfo mons[6]  (6*24=144)

  WebuiOpponentMailbox (260 bytes):
    0   u32 magic  (WUIO = 0x4F495557)
    4   u8  seq
    5   u8  state          (0=idle, 1=request, 2=response)
    6   u8  battlerId
    7   u8  action         (response)
    8   u8  param1         (response)
    9   u8  param2         (response)
    10  u8  targetBattlerLeft
    11  u8  targetBattlerRight
    12  WebuiOppMonInfo controlledMon      (ends 36)
    36  WebuiOppMonInfo targetMonLeft      (ends 60)
    60  WebuiOppMonInfo targetMonRight     (ends 84)
    84  WebuiOppMoveInfo moveInfo          (ends 102)
    102 (pad 2 for align of partyInfo)
    104 WebuiOppPartyInfo partyInfo        (ends 252)
    252 u16 trainerItems[4]                (ends 260)
]]--

local function env(name, default)
    local ok, v = pcall(function() return os.getenv(name) end)
    if ok and v and v ~= "" then return v end
    return default
end

local HOST = env("BATTLEUI_HOST", "127.0.0.1")
local PORT = tonumber(env("BATTLEUI_PORT", "9877")) or 9877
local TOKEN = env("BATTLEUI_TOKEN", "")
local MAGIC = 0x4F495557
local EWRAM_START = 0x02000000
local EWRAM_END   = 0x02040000
local MAILBOX_SIZE = 260
local STATE_IDLE, STATE_REQUEST, STATE_RESPONSE = 0, 1, 2

-- ------------------------------------------------------------------
-- Minimal JSON encoder/decoder (tables, numbers, strings, bools, null).
-- Good enough for our schema; not a full RFC 8259 implementation.
-- ------------------------------------------------------------------
local json = {}

local function json_encode_string(s)
    local r = s:gsub('\\', '\\\\'):gsub('"', '\\"')
        :gsub('\b', '\\b'):gsub('\f', '\\f')
        :gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
    r = r:gsub('[%z\1-\31]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. r .. '"'
end

local function is_array(t)
    local n = 0
    for k, _ in pairs(t) do
        if type(k) ~= "number" then return false end
        if k > n then n = k end
    end
    for i = 1, n do
        if t[i] == nil then return false end
    end
    return true, n
end

function json.encode(v)
    local ty = type(v)
    if v == nil then return "null"
    elseif ty == "boolean" then return v and "true" or "false"
    elseif ty == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "null" end
        if v == math.floor(v) and math.abs(v) < 1e15 then
            return string.format("%d", v)
        end
        return string.format("%.17g", v)
    elseif ty == "string" then return json_encode_string(v)
    elseif ty == "table" then
        local arr, n = is_array(v)
        if arr then
            local parts = {}
            for i = 1, n do parts[i] = json.encode(v[i]) end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, val in pairs(v) do
                parts[#parts+1] = json_encode_string(tostring(k)) .. ":" .. json.encode(val)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    error("cannot encode type " .. ty)
end

local function skip_ws(s, i)
    while i <= #s do
        local c = s:sub(i, i)
        if c ~= " " and c ~= "\t" and c ~= "\n" and c ~= "\r" then return i end
        i = i + 1
    end
    return i
end

local decode_value

local function decode_string(s, i)
    assert(s:sub(i, i) == '"')
    i = i + 1
    local out = {}
    while i <= #s do
        local c = s:sub(i, i)
        if c == '"' then return table.concat(out), i + 1
        elseif c == '\\' then
            local n = s:sub(i+1, i+1)
            if n == 'n' then out[#out+1] = '\n'
            elseif n == 't' then out[#out+1] = '\t'
            elseif n == 'r' then out[#out+1] = '\r'
            elseif n == 'b' then out[#out+1] = '\b'
            elseif n == 'f' then out[#out+1] = '\f'
            elseif n == '"' then out[#out+1] = '"'
            elseif n == '\\' then out[#out+1] = '\\'
            elseif n == '/' then out[#out+1] = '/'
            elseif n == 'u' then
                local hex = s:sub(i+2, i+5)
                out[#out+1] = string.char(tonumber(hex, 16) % 256)
                i = i + 4
            else error("bad escape") end
            i = i + 2
        else
            out[#out+1] = c
            i = i + 1
        end
    end
    error("unterminated string")
end

local function decode_number(s, i)
    local j = i
    while j <= #s and s:sub(j, j):match("[%-0-9%.eE%+]") do j = j + 1 end
    return tonumber(s:sub(i, j-1)), j
end

decode_value = function(s, i)
    i = skip_ws(s, i)
    local c = s:sub(i, i)
    if c == '"' then return decode_string(s, i)
    elseif c == '{' then
        local o, k, v = {}, nil, nil
        i = skip_ws(s, i + 1)
        if s:sub(i, i) == '}' then return o, i + 1 end
        while true do
            i = skip_ws(s, i)
            k, i = decode_string(s, i)
            i = skip_ws(s, i)
            assert(s:sub(i, i) == ':'); i = i + 1
            v, i = decode_value(s, i)
            o[k] = v
            i = skip_ws(s, i)
            local ch = s:sub(i, i)
            if ch == ',' then i = i + 1
            elseif ch == '}' then return o, i + 1
            else error("expected , or }") end
        end
    elseif c == '[' then
        local a = {}
        i = skip_ws(s, i + 1)
        if s:sub(i, i) == ']' then return a, i + 1 end
        while true do
            local v
            v, i = decode_value(s, i)
            a[#a+1] = v
            i = skip_ws(s, i)
            local ch = s:sub(i, i)
            if ch == ',' then i = i + 1
            elseif ch == ']' then return a, i + 1
            else error("expected , or ]") end
        end
    elseif c == 't' then return true, i + 4
    elseif c == 'f' then return false, i + 5
    elseif c == 'n' then return nil, i + 4
    else return decode_number(s, i) end
end

function json.decode(s) local v = decode_value(s, 1); return v end

-- ------------------------------------------------------------------
-- Logging
-- ------------------------------------------------------------------
local function log(msg)
    if console and console.log then console:log("[battleui] " .. msg) else print("[battleui] " .. msg) end
end

-- ------------------------------------------------------------------
-- Memory helpers
-- ------------------------------------------------------------------
local function read_u8(addr)  return emu:read8(addr)  end
local function read_u16(addr) return emu:read16(addr) end
local function read_u32(addr) return emu:read32(addr) end
local function write_u8(addr, v) emu:write8(addr, v) end

-- Read `n` bytes starting at addr into an array of integer byte values.
-- We intentionally do NOT return a Lua string here: the mailbox stores GBA
-- charmap bytes (not UTF-8), which would crash strict JSON consumers.
local function read_byte_array(addr, n)
    local t = {}
    for i = 0, n - 1 do t[i+1] = emu:read8(addr + i) end
    return t
end

-- ------------------------------------------------------------------
-- Mailbox decoding (offsets match the comment block above).
-- ------------------------------------------------------------------
local function read_mon(base)
    return {
        species = read_u16(base + 0),
        hp      = read_u16(base + 2),
        maxHp   = read_u16(base + 4),
        status1 = read_u32(base + 8),
        level   = read_u8 (base + 12),
        nickname = read_byte_array(base + 13, 11),
    }
end

local function read_move_info(base)
    local moves, cur, mx = {}, {}, {}
    for i = 0, 3 do moves[i+1] = read_u16(base + 0 + i*2) end
    for i = 0, 3 do cur[i+1]   = read_u8 (base + 8 + i)   end
    for i = 0, 3 do mx[i+1]    = read_u8 (base + 12 + i)  end
    return {
        moves = moves, currentPp = cur, maxPp = mx,
        monTypes = { read_u8(base + 16), read_u8(base + 17) },
    }
end

local function read_party_info(base)
    local mons = {}
    for i = 0, 5 do mons[i+1] = read_mon(base + 4 + i*24) end
    return {
        firstMonId   = read_u8(base + 0),
        lastMonId    = read_u8(base + 1),
        currentMonId = read_u8(base + 2),
        partnerMonId = read_u8(base + 3),
        mons = mons,
    }
end

local function read_request(addr)
    local items = {}
    for i = 0, 3 do items[i+1] = read_u16(addr + 252 + i*2) end
    return {
        seq       = read_u8(addr + 4),
        battlerId = read_u8(addr + 6),
        targetBattlerLeft  = read_u8(addr + 10),
        targetBattlerRight = read_u8(addr + 11),
        controlledMon  = read_mon(addr + 12),
        targetMonLeft  = read_mon(addr + 36),
        targetMonRight = read_mon(addr + 60),
        moveInfo       = read_move_info(addr + 84),
        partyInfo      = read_party_info(addr + 104),
        trainerItems   = items,
    }
end

-- ------------------------------------------------------------------
-- Mailbox address resolution
-- ------------------------------------------------------------------
local mailbox_addr = nil

local function try_symbol_lookup()
    -- mGBA's scripting API may expose a symbol lookup; try various names.
    if emu and emu.getSymbolValue then
        local ok, v = pcall(function() return emu:getSymbolValue("gWebuiOpponentMailbox") end)
        if ok and type(v) == "number" and v ~= 0 then return v end
    end
    if emu and emu.symbolAddress then
        local ok, v = pcall(function() return emu:symbolAddress("gWebuiOpponentMailbox") end)
        if ok and type(v) == "number" and v ~= 0 then return v end
    end
    return nil
end

local function try_read_addr_file()
    local paths = {
        "tools/battleui/mailbox_addr.txt",
        "./tools/battleui/mailbox_addr.txt",
    }
    for _, p in ipairs(paths) do
        local f = io.open(p, "r")
        if f then
            local s = f:read("*l") or ""
            f:close()
            s = s:gsub("%s+", "")
            if #s > 0 then
                local n = tonumber(s, 16) or tonumber(s)
                if n then return n end
            end
        end
    end
    return nil
end

local function scan_for_magic()
    -- Use bulk readRange when available (one host call instead of 64K) and
    -- search for the little-endian magic bytes at 4-aligned offsets.
    local len = EWRAM_END - EWRAM_START
    local mem = nil
    if emu.readRange then
        local ok, data = pcall(function() return emu:readRange(EWRAM_START, len) end)
        if ok then mem = data end
    end
    if mem and type(mem) == "string" and #mem >= 4 then
        local pat = "\x57\x55\x49\x4F" -- 0x4F495557 little-endian "WUIO"
        local pos = 1
        while true do
            local s = mem:find(pat, pos, true)
            if not s then return nil end
            if ((s - 1) % 4) == 0 then
                return EWRAM_START + (s - 1)
            end
            pos = s + 1
        end
    end
    -- Fallback: per-word scan (slow — only used if readRange is missing).
    for a = EWRAM_START, EWRAM_END - 4, 4 do
        if read_u32(a) == MAGIC then return a end
    end
    return nil
end

local function resolve_mailbox()
    local a = try_symbol_lookup()
    if a then log(string.format("mailbox via symbol lookup: 0x%08x", a)); return a end
    a = try_read_addr_file()
    if a and read_u32(a) == MAGIC then
        log(string.format("mailbox via addr file: 0x%08x", a)); return a
    end
    a = scan_for_magic()
    if a then log(string.format("mailbox via EWRAM scan: 0x%08x", a)); return a end
    return nil
end

-- ------------------------------------------------------------------
-- TCP socket handling (mGBA async sockets; tolerate AGAIN/timeout)
-- ------------------------------------------------------------------
local sock = nil
local rx_buffer = ""
local last_connect_attempt = 0
local CONNECT_COOLDOWN_FRAMES = 60 -- ~1s at 60fps
local frame_counter = 0

local function err_is_transient(err)
    -- Anything that clearly means "no data right now / would block" is benign.
    if err == nil or err == 0 then return true end
    if type(err) == "number" then
        if socket and socket.ERRORS then
            if err == socket.ERRORS.OK or err == socket.ERRORS.AGAIN
               or err == socket.ERRORS.TIMEOUT then return true end
        end
        return false
    end
    if type(err) == "string" then
        local e = err:lower()
        if e:find("again") or e:find("timeout") or e:find("would block")
           or e:find("temporarily unavailable") or e:find("temporary failure")
           or e:find("in progress") then
            return true
        end
    end
    return false
end

local function socket_close()
    if sock then
        pcall(function() sock:close() end)
        sock = nil
    end
    rx_buffer = ""
end

local function pump_receive()
    if not sock then return end
    while true do
        local data, err = sock:receive(4096)
        if data and type(data) == "string" and #data > 0 then
            rx_buffer = rx_buffer .. data
        else
            if not err_is_transient(err) then
                log("disconnected: " .. tostring(err))
                socket_close()
            end
            return
        end
    end
end

local function on_socket_error(_, err)
    if err_is_transient(err) then return end
    log("socket error: " .. tostring(err))
    socket_close()
end

local function socket_try_connect()
    if sock then return end
    if frame_counter - last_connect_attempt < CONNECT_COOLDOWN_FRAMES then return end
    last_connect_attempt = frame_counter
    if not socket or not socket.tcp then
        log("mGBA socket API unavailable")
        return
    end
    local s = socket.tcp()
    if not s then return end
    if s.add then
        pcall(function() s:add("received", pump_receive) end)
        pcall(function() s:add("error", on_socket_error) end)
    end
    local ok, err = s:connect(HOST, PORT)
    -- mGBA's non-blocking connect returns various shapes. Only bail on a
    -- clearly fatal (non-transient) error.
    if (ok == nil or ok == false) and not err_is_transient(err) then
        pcall(function() s:close() end)
        log("connect failed: " .. tostring(err))
        return
    end
    sock = s
    rx_buffer = ""
    log(string.format("connected to %s:%d", HOST, PORT))
    if TOKEN ~= "" then
        local hello = json.encode({ type = "hello", token = TOKEN }) .. "\n"
        local sok, serr = s:send(hello)
        if (sok == nil or sok == false) and not err_is_transient(serr) then
            log("hello send failed: " .. tostring(serr))
            socket_close()
        end
    end
end

local function socket_send_line(tbl)
    if not sock then return false end
    local encoded = json.encode(tbl) .. "\n"
    local ok, err = sock:send(encoded)
    if (ok == nil or ok == false) and not err_is_transient(err) then
        log("send failed: " .. tostring(err))
        socket_close()
        return false
    end
    return true
end

local function pop_line()
    local nl = rx_buffer:find("\n", 1, true)
    if not nl then return nil end
    local line = rx_buffer:sub(1, nl - 1)
    rx_buffer = rx_buffer:sub(nl + 1)
    return line
end

-- ------------------------------------------------------------------
-- Main polling loop
-- ------------------------------------------------------------------
local last_sent_seq = -1
local pending_response = nil
local next_scan_frame = 0
local SCAN_INTERVAL_FRAMES = 60 -- throttle bulk EWRAM scans to 1/s

local function validate_mailbox()
    if not mailbox_addr then return false end
    if read_u32(mailbox_addr) ~= MAGIC then
        log("magic lost (savestate?) — rescanning")
        mailbox_addr = nil
        last_sent_seq = -1
        pending_response = nil
        return false
    end
    return true
end

local function handle_incoming()
    while true do
        local line = pop_line()
        if not line then break end
        local ok, msg = pcall(json.decode, line)
        if ok and type(msg) == "table" and msg.type == "response" then
            pending_response = msg
        end
    end
end

local function write_response(msg)
    if not validate_mailbox() then return false end
    local seq = read_u8(mailbox_addr + 4)
    if msg.seq ~= nil and msg.seq ~= seq then
        log(string.format("stale response seq=%s (current=%d), dropping", tostring(msg.seq), seq))
        return true
    end
    write_u8(mailbox_addr + 7, msg.action or 0)
    write_u8(mailbox_addr + 8, msg.param1 or 0)
    write_u8(mailbox_addr + 9, msg.param2 or 0)
    write_u8(mailbox_addr + 5, STATE_RESPONSE)
    return true
end

local function on_frame()
    frame_counter = frame_counter + 1

    if not mailbox_addr then
        if frame_counter < next_scan_frame then return end
        mailbox_addr = resolve_mailbox()
        if not mailbox_addr then
            next_scan_frame = frame_counter + SCAN_INTERVAL_FRAMES
            return
        end
    end
    if not validate_mailbox() then
        next_scan_frame = frame_counter + SCAN_INTERVAL_FRAMES
        return
    end

    socket_try_connect()
    -- In case mGBA didn't deliver the "received" event (older builds), also
    -- poll-drain once per frame. No-op if nothing is buffered.
    pump_receive()
    handle_incoming()

    if pending_response then
        if write_response(pending_response) then pending_response = nil end
    end

    local state = read_u8(mailbox_addr + 5)
    local seq = read_u8(mailbox_addr + 4)

    if seq ~= last_sent_seq and state == STATE_REQUEST and sock then
        local req = read_request(mailbox_addr)
        req.type = "request"
        if socket_send_line(req) then
            last_sent_seq = seq
            log(string.format("sent request seq=%d battler=%d", seq, req.battlerId))
        end
    end

    if state == STATE_IDLE and last_sent_seq ~= -1 and seq ~= last_sent_seq then
        -- Savestate or fresh init — allow re-send of future requests.
        last_sent_seq = -1
    end
end

-- ------------------------------------------------------------------
-- Registration
-- ------------------------------------------------------------------
if callbacks and callbacks.add then
    callbacks:add("frame", on_frame)
    log("bridge loaded; waiting for mailbox + server")
else
    log("callbacks API unavailable — mGBA 0.10+ required")
end
