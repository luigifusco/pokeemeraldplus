#include "global.h"
#include "remote_opponent.h"

#ifdef REMOTE_OPPONENT

#include "gpu_regs.h"
#include "bg.h"
#include "data.h"
#include "link.h"
#include "main.h"
#include "menu.h"
#include "palette.h"
#include "sprite.h"
#include "string_util.h"
#include "strings.h"
#include "task.h"
#include "text.h"
#include "text_window.h"
#include "window.h"
#include "constants/rgb.h"
#include "constants/moves.h"

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
static EWRAM_DATA u8 sSlaveUiLastStatus = 0xFF;
static EWRAM_DATA u8 sSlaveUiLastPending = 0xFF;
static EWRAM_DATA u8 sSlaveUiLastSelectedSlot = 0xFF;
static EWRAM_DATA u16 sSlaveUiMoves[4];

static const u16 sSlaveSlotColors[] =
{
    RGB(0, 0, 12),
    RGB(0, 0, 18),
    RGB(0, 0, 24),
    RGB(0, 0, 31),
};

enum
{
    SLAVE_UI_STATUS_NO_CONN,
    SLAVE_UI_STATUS_NO_REMOTE_PLAYERS,
    SLAVE_UI_STATUS_NEED_TWO_PLAYERS,
    SLAVE_UI_STATUS_EXCHANGE_INCOMPLETE,
    SLAVE_UI_STATUS_READY,
    SLAVE_UI_STATUS_PENDING,
};

enum
{
    WIN_STATUS,
    WIN_MOVES,
};

static const struct BgTemplate sSlaveBgTemplates[] =
{
    {
        .bg = 0,
        .charBaseIndex = 3,
        .mapBaseIndex = 31,
    },
};

static const struct WindowTemplate sSlaveWindowTemplates[] =
{
    {
        .bg = 0,
        .tilemapLeft = 1,
        .tilemapTop = 1,
        .width = 28,
        .height = 4,
        .paletteNum = 14,
        .baseBlock = 0x001,
    },
    {
        .bg = 0,
        .tilemapLeft = 1,
        .tilemapTop = 6,
        .width = 28,
        .height = 12,
        .paletteNum = 14,
        .baseBlock = 0x001 + (28 * 4),
    },
    DUMMY_WIN_TEMPLATE
};

static const u8 sText_RemoteOpponent[] = _("Remote Opponent");
static const u8 sText_Status[] = _("Status:");
static const u8 sText_NoLink[] = _("No link");
static const u8 sText_WaitingPlayers[] = _("Waiting players");
static const u8 sText_Exchanging[] = _("Exchanging data");
static const u8 sText_Ready[] = _("Ready");
static const u8 sText_ChooseMove[] = _("Choose move");
static const u8 sText_DpadSelectASend[] = _("DPAD selects, A sends");
static const u8 sText_BCancels[] = _("B cancels");
static const u8 sText_Up[] = _("UP");
static const u8 sText_Right[] = _("RIGHT");
static const u8 sText_Down[] = _("DOWN");
static const u8 sText_Left[] = _("LEFT");
static const u8 sText_Dash[] = _("---");
static const u8 sText_ColonSpace[] = _(": ");

static void VBlankCB_RemoteOpponentSlave(void)
{
    TransferPlttBuffer();
}

static void SetSlaveBackdropColor(u16 color)
{
    gPlttBufferUnfaded[0] = color;
    gPlttBufferFaded[0] = color;
}

static const u8 *GetSlaveStatusText(u8 status)
{
    switch (status)
    {
    case SLAVE_UI_STATUS_NO_CONN:
        return sText_NoLink;
    case SLAVE_UI_STATUS_NO_REMOTE_PLAYERS:
    case SLAVE_UI_STATUS_NEED_TWO_PLAYERS:
        return sText_WaitingPlayers;
    case SLAVE_UI_STATUS_EXCHANGE_INCOMPLETE:
        return sText_Exchanging;
    case SLAVE_UI_STATUS_READY:
        return sText_Ready;
    case SLAVE_UI_STATUS_PENDING:
        return sText_ChooseMove;
    }

    return sText_NoLink;
}

static void SlaveUi_DrawStatus(u8 status)
{
    FillWindowPixelBuffer(WIN_STATUS, PIXEL_FILL(0));
    AddTextPrinterParameterized(WIN_STATUS, FONT_NORMAL, sText_RemoteOpponent, 0, 1, TEXT_SKIP_DRAW, NULL);
    AddTextPrinterParameterized(WIN_STATUS, FONT_NORMAL, sText_Status, 0, 17, TEXT_SKIP_DRAW, NULL);
    AddTextPrinterParameterized(WIN_STATUS, FONT_NORMAL, GetSlaveStatusText(status), 48, 17, TEXT_SKIP_DRAW, NULL);
    PutWindowTilemap(WIN_STATUS);
    CopyWindowToVram(WIN_STATUS, COPYWIN_FULL);
}

static const u8 *GetMoveNameOrDash(u16 move)
{
    if (move == MOVE_NONE)
        return sText_Dash;
    return gMoveNames[move];
}

static void SlaveUi_DrawMoves(void)
{
    u8 i;
    u8 y;
    u8 text[64];
    static const u8 *const sDirLabels[MAX_MON_MOVES] =
    {
        sText_Up,
        sText_Right,
        sText_Down,
        sText_Left,
    };

    FillWindowPixelBuffer(WIN_MOVES, PIXEL_FILL(0));

    AddTextPrinterParameterized(WIN_MOVES, FONT_NORMAL, sText_DpadSelectASend, 0, 1, TEXT_SKIP_DRAW, NULL);
    AddTextPrinterParameterized(WIN_MOVES, FONT_NORMAL, sText_BCancels, 0, 17, TEXT_SKIP_DRAW, NULL);

    y = 40;
    for (i = 0; i < MAX_MON_MOVES; i++)
    {
        text[0] = (i == (sSlaveSelectedSlot & 3)) ? '>' : ' ';
        text[1] = ' ';
        text[2] = EOS;
        StringAppend(text, sDirLabels[i]);
        StringAppend(text, sText_ColonSpace);
        StringAppend(text, GetMoveNameOrDash(sSlaveUiMoves[i]));
        AddTextPrinterParameterized(WIN_MOVES, FONT_NORMAL, text, 0, y, TEXT_SKIP_DRAW, NULL);
        y += 16;
    }

    PutWindowTilemap(WIN_MOVES);
    CopyWindowToVram(WIN_MOVES, COPYWIN_FULL);
}

static void SlaveUi_Init(void)
{
    SetGpuReg(REG_OFFSET_DISPCNT, 0);
    ResetSpriteData();
    FreeAllSpritePalettes();
    ResetTasks();
    ResetBgsAndClearDma3BusyFlags(0);
    InitBgsFromTemplates(0, sSlaveBgTemplates, ARRAY_COUNT(sSlaveBgTemplates));
    ResetTempTileDataBuffers();

    if (!InitWindows(sSlaveWindowTemplates))
        return;
    DeactivateAllTextPrinters();

    FillBgTilemapBufferRect(0, 0, 0, 0, DISPLAY_TILE_WIDTH, DISPLAY_TILE_HEIGHT, 0);
    LoadUserWindowBorderGfx(0, 1, BG_PLTT_ID(13));
    LoadUserWindowBorderGfx_(0, 1, BG_PLTT_ID(13));
    Menu_LoadStdPal();

    ClearWindowTilemap(WIN_STATUS);
    ClearWindowTilemap(WIN_MOVES);
    PutWindowTilemap(WIN_STATUS);
    PutWindowTilemap(WIN_MOVES);

    ShowBg(0);
    SetGpuReg(REG_OFFSET_DISPCNT, DISPCNT_MODE_0 | DISPCNT_BG0_ON);

    sSlaveUiLastStatus = 0xFF;
    sSlaveUiLastPending = 0xFF;
    sSlaveUiLastSelectedSlot = 0xFF;
    sSlaveUiMoves[0] = MOVE_NONE;
    sSlaveUiMoves[1] = MOVE_NONE;
    sSlaveUiMoves[2] = MOVE_NONE;
    sSlaveUiMoves[3] = MOVE_NONE;
}

void CB2_InitRemoteOpponentSlave(void)
{
    SetVBlankCallback(NULL);
    DmaFill16(3, 0, (void *)VRAM, VRAM_SIZE);
    DmaFill32(3, 0, (void *)OAM, OAM_SIZE);
    DmaFill16(3, 0, (void *)PLTT, PLTT_SIZE);
    ResetPaletteFade();
    SlaveUi_Init();

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
    u8 uiStatus;

    RemoteOpponent_OpenLinkIfNeeded();

    // Ensure the link module's internal tasks (if any) can run.
    RunTasks();

    sSlaveFrameCounter++;

    // Visual status cue (color + text):
    // - red: serial link not established
    // - orange: connected but remote player blocks not received yet
    // - yellow: remote players received but player count < 2
    // - magenta: player data exchange incomplete / linkType mismatch
    // - green: ready, no pending request
    // - blue shades: pending request (shade indicates selected slot)
    if (!IsLinkConnectionEstablished())
    {
        SetSlaveBackdropColor(RGB(31, 0, 0));
        uiStatus = SLAVE_UI_STATUS_NO_CONN;
    }
    else if (!gReceivedRemoteLinkPlayers)
    {
        SetSlaveBackdropColor(RGB(31, 12, 0));
        uiStatus = SLAVE_UI_STATUS_NO_REMOTE_PLAYERS;
    }
    else if (GetLinkPlayerCount_2() < 2)
    {
        SetSlaveBackdropColor(RGB(31, 31, 0));
        uiStatus = SLAVE_UI_STATUS_NEED_TWO_PLAYERS;
    }
    else if (!IsLinkPlayerDataExchangeComplete())
    {
        SetSlaveBackdropColor(RGB(31, 0, 31));
        uiStatus = SLAVE_UI_STATUS_EXCHANGE_INCOMPLETE;
    }
    else if (!sSlavePending)
    {
        SetSlaveBackdropColor(RGB(0, 31, 0));
        uiStatus = SLAVE_UI_STATUS_READY;
    }
    else
    {
        SetSlaveBackdropColor(sSlaveSlotColors[sSlaveSelectedSlot & 3]);
        uiStatus = SLAVE_UI_STATUS_PENDING;
    }

    if (uiStatus != sSlaveUiLastStatus)
    {
        sSlaveUiLastStatus = uiStatus;
        SlaveUi_DrawStatus(uiStatus);
    }

    // Accept new requests at any time; the latest request wins.
    if (RemoteOpponent_Slave_TryRecvMoveRequest(&seq, &battlerId, moves))
    {
        sSlavePending = TRUE;
        sSlavePendingSeq = seq;
        sSlaveSelectedSlot = 0;

        sSlaveUiMoves[0] = moves[0];
        sSlaveUiMoves[1] = moves[1];
        sSlaveUiMoves[2] = moves[2];
        sSlaveUiMoves[3] = moves[3];
        SlaveUi_DrawStatus(SLAVE_UI_STATUS_PENDING);
        SlaveUi_DrawMoves();
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

    if (sSlaveSelectedSlot != sSlaveUiLastSelectedSlot)
    {
        sSlaveUiLastSelectedSlot = sSlaveSelectedSlot;
        SlaveUi_DrawMoves();
    }

    if (gMain.newKeys & A_BUTTON)
    {
        if (RemoteOpponent_Slave_SendMoveChoice(sSlavePendingSeq, sSlaveSelectedSlot))
        {
            sSlavePending = FALSE;
            SlaveUi_DrawStatus(SLAVE_UI_STATUS_READY);
        }
    }

    if (gMain.newKeys & B_BUTTON)
    {
        sSlavePending = FALSE;
        SlaveUi_DrawStatus(SLAVE_UI_STATUS_READY);
    }
}

#endif // REMOTE_OPPONENT
