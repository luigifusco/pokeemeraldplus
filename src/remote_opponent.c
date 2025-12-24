#include "global.h"
#include "remote_opponent.h"

#ifdef REMOTE_OPPONENT

#include "gpu_regs.h"
#include "link.h"
#include "main.h"
#include "palette.h"
#include "sprite.h"
#include "task.h"
#include "constants/rgb.h"

// Chosen to not collide with existing LINKTYPE_* constants.
#define LINKTYPE_REMOTE_OPPONENT 0xCEFA

enum
{
    REMOTE_OPP_MSG_REQUEST_MOVE = 1,
    REMOTE_OPP_MSG_CHOOSE_MOVE = 2,
};

struct RemoteOppRequest
{
    u8 type;
    u8 seq;
    u8 battlerId;
    u8 unused;
    u16 moves[4];
};

struct RemoteOppResponse
{
    u8 type;
    u8 seq;
    u8 moveSlot;
    u8 unused;
};

static EWRAM_DATA bool8 sRemoteOppLinkOpened = FALSE;
static EWRAM_DATA u8 sRemoteOppHandshakeDelay = 0;
static EWRAM_DATA bool8 sRemoteOppWasReady = FALSE;
static EWRAM_DATA u16 sRemoteOppNoConnFrames = 0;
static EWRAM_DATA u16 sRemoteOppReconnectCooldown = 0;
static EWRAM_DATA u8 sSlavePending = FALSE;
static EWRAM_DATA u8 sSlavePendingSeq = 0;
static EWRAM_DATA u8 sSlaveSelectedSlot = 0;
static EWRAM_DATA u16 sSlaveFrameCounter = 0;

static const u16 sSlaveSlotColors[] =
{
    RGB(0, 0, 12),
    RGB(0, 0, 18),
    RGB(0, 0, 24),
    RGB(0, 0, 31),
};

static void VBlankCB_RemoteOpponentSlave(void)
{
    TransferPlttBuffer();
}

static void SetSlaveBackdropColor(u16 color)
{
    gPlttBufferUnfaded[0] = color;
    gPlttBufferFaded[0] = color;
}

void CB2_InitRemoteOpponentSlave(void)
{
    // Minimal init so the slave ROM is visibly alive (the original MVP loop was display-less).
    SetVBlankCallback(NULL);
    SetGpuReg(REG_OFFSET_DISPCNT, DISPCNT_MODE_0);
    SetGpuReg(REG_OFFSET_BG0HOFS, 0);
    SetGpuReg(REG_OFFSET_BG0VOFS, 0);
    SetGpuReg(REG_OFFSET_BG1HOFS, 0);
    SetGpuReg(REG_OFFSET_BG1VOFS, 0);
    SetGpuReg(REG_OFFSET_BG2HOFS, 0);
    SetGpuReg(REG_OFFSET_BG2VOFS, 0);
    SetGpuReg(REG_OFFSET_BG3HOFS, 0);
    SetGpuReg(REG_OFFSET_BG3VOFS, 0);
    SetGpuReg(REG_OFFSET_WIN0H, 0);
    SetGpuReg(REG_OFFSET_WIN0V, 0);
    SetGpuReg(REG_OFFSET_WIN1H, 0);
    SetGpuReg(REG_OFFSET_WIN1V, 0);
    SetGpuReg(REG_OFFSET_WININ, 0);
    SetGpuReg(REG_OFFSET_WINOUT, 0);
    SetGpuReg(REG_OFFSET_BLDCNT, 0);
    SetGpuReg(REG_OFFSET_BLDALPHA, 0);
    SetGpuReg(REG_OFFSET_BLDY, 0);

    DmaFill16(3, 0, (void *)VRAM, VRAM_SIZE);
    DmaFill32(3, 0, (void *)OAM, OAM_SIZE);
    DmaFill16(3, 0, (void *)PLTT, PLTT_SIZE);

    ResetPaletteFade();
    ResetTasks();
    ResetSpriteData();
    FreeAllSpritePalettes();

    sSlaveFrameCounter = 0;
    sSlavePending = FALSE;
    sSlavePendingSeq = 0;
    sSlaveSelectedSlot = 0;

    // Start with a visible "not connected" color.
    SetSlaveBackdropColor(RGB(31, 0, 0));

    EnableInterrupts(INTR_FLAG_VBLANK);
    SetVBlankCallback(VBlankCB_RemoteOpponentSlave);
    SetMainCallback2(CB2_RemoteOpponentSlave);
}

static bool32 TryRecvPacket(u8 *outFromId, const u8 **outData, u16 *outSize)
{
    u8 i;
    u8 status;

    status = GetBlockReceivedStatus();
    if (status == 0)
        return FALSE;

    for (i = 0; i < MAX_LINK_PLAYERS; i++)
    {
        if ((status & (1 << i)) && i != GetMultiplayerId())
        {
            // All blocks share the same recv buffer; size is not explicitly given here.
            // Our packets are small; we just read the leading bytes we need.
            *outFromId = i;
            *outData = (const u8 *)gBlockRecvBuffer[i];
            *outSize = BLOCK_BUFFER_SIZE;
            ResetBlockReceivedFlag(i);
            return TRUE;
        }
    }

    return FALSE;
}

void RemoteOpponent_OpenLinkIfNeeded(void)
{
    // Remote opponent runs "headless" in the overworld; link errors should not
    // kick the game into the standard communication error screen.
    SetSuppressLinkErrorMessage(TRUE);

    // The serial IRQ handler calls gMain.serialCallback; ensure link.c's SerialCB is installed.
    // Some parts of the game (and soft resets) can clear/replace it.
    if (gMain.serialCallback != SerialCB)
        SetSerialCallback(SerialCB);

    if (sRemoteOppReconnectCooldown != 0)
        sRemoteOppReconnectCooldown--;

    // Watchdog: if we never reach a connection-established state for too long,
    // force a reopen. This helps recover from silent CloseLink() calls when link
    // errors are suppressed, and from emulator reset edge cases.
    if (sRemoteOppLinkOpened && !IsLinkConnectionEstablished())
    {
        if (sRemoteOppNoConnFrames < 0xFFFF)
            sRemoteOppNoConnFrames++;
    }
    else
    {
        sRemoteOppNoConnFrames = 0;
    }

    // If we were previously fully connected but the peer vanished (e.g. slave reset),
    // force a clean reopen so player-data exchange can restart.
    // Avoid doing this during battles; battle code already has timeouts/fallback.
    if (sRemoteOppLinkOpened
     && !gMain.inBattle
     && sRemoteOppReconnectCooldown == 0
     && (HasLinkErrorOccurred()
      || (sRemoteOppWasReady && GetLinkPlayerCount_2() < 2)
      || (sRemoteOppNoConnFrames > 600)))
    {
        CloseLink();
        sRemoteOppLinkOpened = FALSE;
        sRemoteOppHandshakeDelay = 0;
        sRemoteOppWasReady = FALSE;
        sRemoteOppNoConnFrames = 0;
        sRemoteOppReconnectCooldown = 60;
    }

    if (!sRemoteOppLinkOpened)
    {
        // Ensure both ROMs advertise the same linkType so player data exchange completes.
        gLinkType = LINKTYPE_REMOTE_OPPONENT;

        // The serial IRQ handler calls gMain.serialCallback; in normal flow the intro sets this.
        // Our master/slave builds can open link outside of that flow, so ensure it's set.
        SetSerialCallback(SerialCB);

        OpenLink();
        sRemoteOppLinkOpened = TRUE;
        // OpenLink() normally uses a task to trigger the handshake a few frames later.
        // The slave build runs a minimal loop without the usual task scheduler, so we
        // also advance the link state here to ensure the handshake progresses.
        sRemoteOppHandshakeDelay = 5;
        sRemoteOppNoConnFrames = 0;
    }

    if (sRemoteOppLinkOpened && sRemoteOppHandshakeDelay != 0)
    {
        sRemoteOppHandshakeDelay--;
        if (sRemoteOppHandshakeDelay == 0)
            gShouldAdvanceLinkState = 1;
    }

    // Important: the vanilla handshake requires the master to assert MASTER_HANDSHAKE
    // once it detects 2+ players. Normally this is driven by link UI flow; in this
    // mod we don't go through those screens, so we auto-advance the handshake here.
    if (sRemoteOppLinkOpened
     && gLink.state == LINK_STATE_HANDSHAKE
     && gLink.isMaster == LINK_MASTER
     && gLink.playerCount > 1)
    {
        gShouldAdvanceLinkState = 1;
    }

    // Track whether we have ever reached a "ready" state, to enable reconnection logic.
    if (!sRemoteOppWasReady && RemoteOpponent_IsReady())
        sRemoteOppWasReady = TRUE;
}

bool32 RemoteOpponent_IsReady(void)
{
    if (!sRemoteOppLinkOpened)
        return FALSE;

    if (!gReceivedRemoteLinkPlayers)
        return FALSE;

    if (GetLinkPlayerCount_2() < 2)
        return FALSE;

    if (!IsLinkConnectionEstablished())
        return FALSE;

    if (!IsLinkPlayerDataExchangeComplete())
        return FALSE;

    return TRUE;
}

bool32 RemoteOpponent_Master_SendMoveRequest(u8 seq, u8 battlerId, const u16 moves[4])
{
    struct RemoteOppRequest req;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!IsLinkTaskFinished())
        return FALSE;

    req.type = REMOTE_OPP_MSG_REQUEST_MOVE;
    req.seq = seq;
    req.battlerId = battlerId;
    req.unused = 0;
    req.moves[0] = moves[0];
    req.moves[1] = moves[1];
    req.moves[2] = moves[2];
    req.moves[3] = moves[3];

    return SendBlock(BitmaskAllOtherLinkPlayers(), &req, sizeof(req));
}

bool32 RemoteOpponent_Master_TryRecvMoveChoice(u8 expectedSeq, u8 *outMoveSlot)
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppResponse *resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;

    resp = (const struct RemoteOppResponse *)data;
    if (resp->type != REMOTE_OPP_MSG_CHOOSE_MOVE)
        return FALSE;

    if (resp->seq != expectedSeq)
        return FALSE;

    *outMoveSlot = resp->moveSlot;
    return TRUE;
}

bool32 RemoteOpponent_Slave_TryRecvMoveRequest(u8 *outSeq, u8 *outBattlerId, u16 outMoves[4])
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppRequest *req;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;

    req = (const struct RemoteOppRequest *)data;
    if (req->type != REMOTE_OPP_MSG_REQUEST_MOVE)
        return FALSE;

    *outSeq = req->seq;
    *outBattlerId = req->battlerId;
    outMoves[0] = req->moves[0];
    outMoves[1] = req->moves[1];
    outMoves[2] = req->moves[2];
    outMoves[3] = req->moves[3];

    return TRUE;
}

bool32 RemoteOpponent_Slave_SendMoveChoice(u8 seq, u8 moveSlot)
{
    struct RemoteOppResponse resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!IsLinkTaskFinished())
        return FALSE;

    resp.type = REMOTE_OPP_MSG_CHOOSE_MOVE;
    resp.seq = seq;
    resp.moveSlot = moveSlot;
    resp.unused = 0;

    return SendBlock(BitmaskAllOtherLinkPlayers(), &resp, sizeof(resp));
}

void CB2_RemoteOpponentSlave(void)
{
    u8 seq;
    u8 battlerId;
    u16 moves[4];

    RemoteOpponent_OpenLinkIfNeeded();

    // Ensure the link module's internal tasks (if any) can run.
    RunTasks();

    sSlaveFrameCounter++;

    // Visual status cue via backdrop color:
    // - red: serial link not established
    // - orange: connected but remote player blocks not received yet
    // - yellow: remote players received but player count < 2
    // - magenta: player data exchange incomplete / linkType mismatch
    // - green: ready, no pending request
    // - blue shades: pending request (shade indicates selected slot)
    if (!IsLinkConnectionEstablished())
    {
        SetSlaveBackdropColor(RGB(31, 0, 0));
    }
    else if (!gReceivedRemoteLinkPlayers)
    {
        SetSlaveBackdropColor(RGB(31, 12, 0));
    }
    else if (GetLinkPlayerCount_2() < 2)
    {
        SetSlaveBackdropColor(RGB(31, 31, 0));
    }
    else if (!IsLinkPlayerDataExchangeComplete())
    {
        SetSlaveBackdropColor(RGB(31, 0, 31));
    }
    else if (!sSlavePending)
    {
        SetSlaveBackdropColor(RGB(0, 31, 0));
    }
    else
    {
        SetSlaveBackdropColor(sSlaveSlotColors[sSlaveSelectedSlot & 3]);
    }

    // Accept new requests at any time; the latest request wins.
    if (RemoteOpponent_Slave_TryRecvMoveRequest(&seq, &battlerId, moves))
    {
        sSlavePending = TRUE;
        sSlavePendingSeq = seq;
        sSlaveSelectedSlot = 0;
    }

    if (!sSlavePending)
        return;

    // Minimal, display-less UI:
    // - DPAD sets the slot
    // - A sends
    // - B cancels (falls back to slot 0 if master times out)
    if (gMain.newKeys & DPAD_UP)
        sSlaveSelectedSlot = 0;
    else if (gMain.newKeys & DPAD_RIGHT)
        sSlaveSelectedSlot = 1;
    else if (gMain.newKeys & DPAD_DOWN)
        sSlaveSelectedSlot = 2;
    else if (gMain.newKeys & DPAD_LEFT)
        sSlaveSelectedSlot = 3;

    if (gMain.newKeys & A_BUTTON)
    {
        if (RemoteOpponent_Slave_SendMoveChoice(sSlavePendingSeq, sSlaveSelectedSlot))
            sSlavePending = FALSE;
    }

    if (gMain.newKeys & B_BUTTON)
        sSlavePending = FALSE;
}

#endif // REMOTE_OPPONENT
