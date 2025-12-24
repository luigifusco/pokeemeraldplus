#include "global.h"
#include "remote_opponent.h"

#ifdef REMOTE_OPPONENT

#include "gpu_regs.h"
#include "bg.h"
#include "data.h"
#include "gba/defines.h"
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
#include "battle_main.h"
#include "pokemon.h"
#include "constants/rgb.h"
#include "constants/battle.h"
#include "constants/moves.h"
#include "constants/characters.h"

// Chosen to not collide with existing LINKTYPE_* constants.
#define LINKTYPE_REMOTE_OPPONENT 0xCEFA

enum
{
    REMOTE_OPP_MSG_REQUEST_MOVE = 1,
    REMOTE_OPP_MSG_CHOOSE_MOVE = 2,
    REMOTE_OPP_MSG_REQUEST_ACTION = 3,
    REMOTE_OPP_MSG_CHOOSE_ACTION = 4,
};

struct RemoteOppRequest
{
    u8 type;
    u8 seq;
    u8 battlerId;
    u8 unused;
    struct RemoteOpponentMonInfo controlledMon;
    struct RemoteOpponentMonInfo targetMon;
    struct RemoteOpponentMoveInfo moveInfo;
};

struct RemoteOppResponse
{
    u8 type;
    u8 seq;
    u8 battlerId;
    u8 moveSlot;
};

struct RemoteOppActionRequest
{
    u8 type;
    u8 seq;
    u8 battlerId;
    u8 unused;
    struct RemoteOpponentMonInfo controlledMon;
    struct RemoteOpponentMonInfo targetMon;
    struct RemoteOpponentPartyInfo party;
};

struct RemoteOppActionResponse
{
    u8 type;
    u8 seq;
    u8 battlerId;
    u8 action;
    u8 data;
    u8 unused;
};

static EWRAM_DATA bool8 sRemoteOppLinkOpened = FALSE;
static EWRAM_DATA u8 sRemoteOppHandshakeDelay = 0;
static EWRAM_DATA bool8 sRemoteOppWasReady = FALSE;
static EWRAM_DATA u16 sRemoteOppNoConnFrames = 0;
static EWRAM_DATA u16 sRemoteOppReconnectCooldown = 0;
static EWRAM_DATA u8 sSlavePending = FALSE;
static EWRAM_DATA u8 sSlavePendingSeq = 0;
static EWRAM_DATA u8 sSlavePendingBattlerId = 0;
static EWRAM_DATA u8 sSlaveSelectedSlot = 0;
static EWRAM_DATA u8 sSlavePendingIsAction = FALSE;
static EWRAM_DATA u8 sSlaveActionCursor = 0;
static EWRAM_DATA u8 sSlaveActionSubscreen = 0;
static EWRAM_DATA u16 sSlaveFrameCounter = 0;
static EWRAM_DATA u8 sSlaveUiLastStatus = 0xFF;
static EWRAM_DATA u8 sSlaveUiLastPending = 0xFF;
static EWRAM_DATA u8 sSlaveUiLastSelectedSlot = 0xFF;
static EWRAM_DATA struct RemoteOpponentMonInfo sSlaveUiControlledMon;
static EWRAM_DATA struct RemoteOpponentMonInfo sSlaveUiTargetMon;
static EWRAM_DATA struct RemoteOpponentMoveInfo sSlaveUiMoveInfo;
static EWRAM_DATA struct RemoteOpponentPartyInfo sSlaveUiPartyInfo;

#ifdef REMOTE_OPPONENT_MASTER
static EWRAM_DATA bool8 sMasterHasCachedPacket = FALSE;
static EWRAM_DATA u8 sMasterCachedPacket[BLOCK_BUFFER_SIZE];
static EWRAM_DATA u8 sMasterCachedFromId = 0;
static EWRAM_DATA u16 sMasterCachedSize = 0;
#endif

#ifdef REMOTE_OPPONENT_SLAVE
static EWRAM_DATA bool8 sSlaveHasCachedPacket = FALSE;
static EWRAM_DATA u8 sSlaveCachedPacket[BLOCK_BUFFER_SIZE];
static EWRAM_DATA u8 sSlaveCachedFromId = 0;
static EWRAM_DATA u16 sSlaveCachedSize = 0;
#endif

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
    WIN_MAIN,
};

static const struct BgTemplate sSlaveBgTemplates[] =
{
    {
        .bg = 0,
        // Use charblock 2 so BG tile graphics don't overlap screenblock 31.
        .charBaseIndex = 2,
        .mapBaseIndex = 31,
    },
};

static const struct WindowTemplate sSlaveWindowTemplates[] =
{
    {
        .bg = 0,
        .tilemapLeft = 1,
        .tilemapTop = 0,
        .width = 28,
        .height = 16,
        .paletteNum = 14,
        // Keep tile 0 free/blank (it may be used by the cleared BG tilemap).
        .baseBlock = 0x014,
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
static const u8 sText_ControlsShort[] = _("A Select  B Back");
static const u8 sText_ChooseAction[] = _("Party / Switch");
static const u8 sText_Fight[] = _("FIGHT");
static const u8 sText_Switch[] = _("SWITCH");
static const u8 sText_ControlsAction[] = _("A Select  B Cancel");
static const u8 sText_ControlsParty[] = _("A Switch  B Back");
static const u8 sText_Up[] = _("UP");
static const u8 sText_Right[] = _("RIGHT");
static const u8 sText_Down[] = _("DOWN");
static const u8 sText_Left[] = _("LEFT");
static const u8 sText_Dash[] = _("---");
static const u8 sText_ColonSpace[] = _(": ");
static const u8 sText_Enemy[] = _("ENEMY ");
static const u8 sText_You[] = _("YOU ");
static const u8 sText_SpaceLv[] = _(" Lv");
static const u8 sText_SpaceHP[] = _(" HP ");
static const u8 sText_SpacePP[] = _(" PP ");
static const u8 sText_SpaceType[] = _("TYPE ");
static const u8 sText_SpaceStatus[] = _(" ");
static const u8 sText_Slash[] = _("/");
static const u8 sText_Space[] = _(" ");
static const u8 sText_SLP[] = _("SLP");
static const u8 sText_PSN[] = _("PSN");
static const u8 sText_TOX[] = _("TOX");
static const u8 sText_BRN[] = _("BRN");
static const u8 sText_FRZ[] = _("FRZ");
static const u8 sText_PAR[] = _("PAR");

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
    // FONT_NORMAL is 16px tall; use 16px line spacing to avoid overlap.
    // Fill with the font BG color so text doesn't appear in "boxes".
    FillWindowPixelBuffer(WIN_MAIN, PIXEL_FILL(1));
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_RemoteOpponent, 0, 0, 0, NULL);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_Status, 0, 16, 0, NULL);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, GetSlaveStatusText(status), 56, 16, 0, NULL);
    PutWindowTilemap(WIN_MAIN);
    CopyWindowToVram(WIN_MAIN, COPYWIN_FULL);
}

static const u8 *GetMoveNameOrDash(u16 move)
{
    if (move == MOVE_NONE)
        return sText_Dash;
    return gMoveNames[move];
}

static const u8 *GetStatus1ShortString(u32 status1)
{
    if (status1 & STATUS1_SLEEP)
        return sText_SLP;
    if (status1 & STATUS1_TOXIC_POISON)
        return sText_TOX;
    if (status1 & STATUS1_POISON)
        return sText_PSN;
    if (status1 & STATUS1_BURN)
        return sText_BRN;
    if (status1 & STATUS1_FREEZE)
        return sText_FRZ;
    if (status1 & STATUS1_PARALYSIS)
        return sText_PAR;
    return NULL;
}

static void BuildMonLine(u8 *dst, const u8 *prefix, const struct RemoteOpponentMonInfo *mon)
{
    const u8 *statusStr;
    u8 *ptr;

    ptr = StringCopy(dst, prefix);
    ptr = StringAppend(ptr, mon->nickname);
    ptr = StringAppend(ptr, sText_SpaceLv);
    ptr = ConvertIntToDecimalStringN(ptr, mon->level, STR_CONV_MODE_LEFT_ALIGN, 3);
    ptr = StringAppend(ptr, sText_SpaceHP);
    ptr = ConvertIntToDecimalStringN(ptr, mon->hp, STR_CONV_MODE_LEFT_ALIGN, 3);
    ptr = StringAppend(ptr, sText_Slash);
    ptr = ConvertIntToDecimalStringN(ptr, mon->maxHp, STR_CONV_MODE_LEFT_ALIGN, 3);

    statusStr = GetStatus1ShortString(mon->status1);
    if (statusStr != NULL)
    {
        ptr = StringAppend(ptr, sText_SpaceStatus);
        ptr = StringAppend(ptr, statusStr);
    }
}

static void SlaveUi_DrawMoves(void)
{
    u8 i;
    u8 y;
    u8 text[64];
    u8 line[128];
    u16 selectedMove;
    u8 moveType;

    // Layout uses 8 lines at 16px each (fits exactly in a 16-tile window).
    FillWindowPixelBuffer(WIN_MAIN, PIXEL_FILL(1));

    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_ChooseMove, 0, 0, 0, NULL);

    BuildMonLine(line, sText_Enemy, &sSlaveUiControlledMon);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, line, 0, 16, 0, NULL);

    BuildMonLine(line, sText_You, &sSlaveUiTargetMon);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, line, 0, 32, 0, NULL);

    y = 48;
    for (i = 0; i < MAX_MON_MOVES; i++)
    {
        u8 *ptr;

        if (i == (sSlaveSelectedSlot & 3))
            AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, gText_SelectorArrow2, 0, y, 0, NULL);

        text[0] = EOS;
        StringAppend(text, GetMoveNameOrDash(sSlaveUiMoveInfo.moves[i]));

        if (sSlaveUiMoveInfo.moves[i] != MOVE_NONE)
        {
            ptr = StringAppend(text, sText_SpacePP);
            ptr = ConvertIntToDecimalStringN(ptr, sSlaveUiMoveInfo.currentPp[i], STR_CONV_MODE_LEFT_ALIGN, 2);
            ptr = StringAppend(ptr, sText_Slash);
            ptr = ConvertIntToDecimalStringN(ptr, sSlaveUiMoveInfo.maxPp[i], STR_CONV_MODE_LEFT_ALIGN, 2);
        }
        AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, text, 8, y, 0, NULL);
        y += 16;
    }

    // Bottom line: TYPE + controls (keeps everything on-screen without overlap).
    selectedMove = sSlaveUiMoveInfo.moves[sSlaveSelectedSlot & 3];
    StringCopy(line, sText_SpaceType);
    if (selectedMove != MOVE_NONE)
    {
        moveType = gBattleMoves[selectedMove].type;
        StringAppend(line, gTypeNames[moveType]);
    }
    else
    {
        StringAppend(line, sText_Dash);
    }
    StringAppend(line, sText_Space);
    StringAppend(line, sText_ControlsShort);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, line, 0, 112, 0, NULL);

    PutWindowTilemap(WIN_MAIN);
    CopyWindowToVram(WIN_MAIN, COPYWIN_FULL);
}

enum
{
    SLAVE_ACTION_SUBSCREEN_MENU,
    SLAVE_ACTION_SUBSCREEN_PARTY,
};

static void SlaveUi_DrawActionMenu(void)
{
    u8 line[128];

    FillWindowPixelBuffer(WIN_MAIN, PIXEL_FILL(1));

    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_ChooseAction, 0, 0, 0, NULL);

    BuildMonLine(line, sText_Enemy, &sSlaveUiControlledMon);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, line, 0, 16, 0, NULL);

    BuildMonLine(line, sText_You, &sSlaveUiTargetMon);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, line, 0, 32, 0, NULL);

    if (sSlaveActionCursor == 0)
        AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, gText_SelectorArrow2, 0, 56, 0, NULL);
    else
        AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, gText_SelectorArrow2, 0, 72, 0, NULL);

    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_Fight, 8, 56, 0, NULL);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_Switch, 8, 72, 0, NULL);
    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_ControlsAction, 0, 112, 0, NULL);

    PutWindowTilemap(WIN_MAIN);
    CopyWindowToVram(WIN_MAIN, COPYWIN_FULL);
}

static void BuildPartyLine(u8 *dst, u8 slot, const struct RemoteOpponentPartyInfo *party)
{
    const struct RemoteOpponentMonInfo *mon = &party->mons[slot];
    const u8 *statusStr;
    u8 *ptr;

    // Line begins with "<n>: " and then the mon summary.
    dst[0] = CHAR_0 + (slot + 1);
    dst[1] = CHAR_COLON;
    dst[2] = CHAR_SPACE;
    dst[3] = EOS;

    ptr = dst + 3;

    // Outside the valid half-party range (two opponents, etc)
    if (slot < party->firstMonId || slot >= party->lastMonId)
    {
        StringAppend(ptr, sText_Dash);
        return;
    }

    if (mon->species == SPECIES_NONE)
    {
        StringAppend(ptr, sText_Dash);
        return;
    }

    ptr = StringAppend(ptr, mon->nickname);
    ptr = StringAppend(ptr, sText_SpaceLv);
    ptr = ConvertIntToDecimalStringN(ptr, mon->level, STR_CONV_MODE_LEFT_ALIGN, 3);
    ptr = StringAppend(ptr, sText_SpaceHP);
    ptr = ConvertIntToDecimalStringN(ptr, mon->hp, STR_CONV_MODE_LEFT_ALIGN, 3);
    ptr = StringAppend(ptr, sText_Slash);
    ptr = ConvertIntToDecimalStringN(ptr, mon->maxHp, STR_CONV_MODE_LEFT_ALIGN, 3);

    statusStr = GetStatus1ShortString(mon->status1);
    if (statusStr != NULL)
    {
        ptr = StringAppend(ptr, sText_SpaceStatus);
        ptr = StringAppend(ptr, statusStr);
    }
}

static void SlaveUi_DrawParty(void)
{
    u8 i;
    u8 y;
    u8 line[128];

    FillWindowPixelBuffer(WIN_MAIN, PIXEL_FILL(1));

    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_ChooseAction, 0, 0, 0, NULL);

    y = 16;
    for (i = 0; i < PARTY_SIZE; i++)
    {
        if (i == (sSlaveSelectedSlot % PARTY_SIZE))
            AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, gText_SelectorArrow2, 0, y, 0, NULL);
        BuildPartyLine(line, i, &sSlaveUiPartyInfo);
        AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, line, 8, y, 0, NULL);
        y += 16;
    }

    AddTextPrinterParameterized(WIN_MAIN, FONT_NORMAL, sText_ControlsParty, 0, 112, 0, NULL);

    PutWindowTilemap(WIN_MAIN);
    CopyWindowToVram(WIN_MAIN, COPYWIN_FULL);
}

static bool8 SlaveUi_IsValidSwitchSlot(u8 slot)
{
    const struct RemoteOpponentMonInfo *mon;

    if (slot >= PARTY_SIZE)
        return FALSE;
    if (slot < sSlaveUiPartyInfo.firstMonId || slot >= sSlaveUiPartyInfo.lastMonId)
        return FALSE;
    if (slot == sSlaveUiPartyInfo.currentMonId || slot == sSlaveUiPartyInfo.partnerMonId)
        return FALSE;

    mon = &sSlaveUiPartyInfo.mons[slot];
    if (mon->species == SPECIES_NONE)
        return FALSE;
    if (mon->hp == 0)
        return FALSE;

    return TRUE;
}

static void SlaveUi_Init(void)
{
    SetGpuReg(REG_OFFSET_DISPCNT, 0);
    SetGpuReg(REG_OFFSET_BG0HOFS, 0);
    SetGpuReg(REG_OFFSET_BG0VOFS, 0);
    ResetSpriteData();
    FreeAllSpritePalettes();
    ResetTasks();
    ResetBgsAndClearDma3BusyFlags(0);
    InitBgsFromTemplates(0, sSlaveBgTemplates, ARRAY_COUNT(sSlaveBgTemplates));
    ResetTempTileDataBuffers();

    if (!InitWindows(sSlaveWindowTemplates))
        return;
    DeactivateAllTextPrinters();

    // Clear the full BG0 tilemap (32x32) to tile 0. Even though only 30x20 tiles are visible,
    // a non-zero scroll offset (or other engine state) can reveal off-screen rows/cols.
    FillBgTilemapBufferRect(0, 0, 0, 0, 32, 32, 0);
    Menu_LoadStdPal();

    // Make absolutely sure BG tile 0 is blank.
    // If any unoccupied tilemap area points at tile 0, we want it to render empty (not font/border garbage).
    DmaFill32(3, 0, (void *)BG_CHAR_ADDR(sSlaveBgTemplates[0].charBaseIndex), 32);

    // Push the cleared tilemap buffer to VRAM so there are no leftover tiles.
    CopyBgTilemapBufferToVram(0);

    ClearWindowTilemap(WIN_MAIN);
    PutWindowTilemap(WIN_MAIN);

    // Ensure the window tile gfx is initialized in VRAM.
    FillWindowPixelBuffer(WIN_MAIN, PIXEL_FILL(0));
    CopyWindowToVram(WIN_MAIN, COPYWIN_FULL);

    ShowBg(0);
    SetGpuReg(REG_OFFSET_DISPCNT, DISPCNT_MODE_0 | DISPCNT_BG0_ON);

    sSlaveUiLastStatus = 0xFF;
    sSlaveUiLastPending = 0xFF;
    sSlaveUiLastSelectedSlot = 0xFF;
    sSlaveUiMoveInfo.moves[0] = MOVE_NONE;
    sSlaveUiMoveInfo.moves[1] = MOVE_NONE;
    sSlaveUiMoveInfo.moves[2] = MOVE_NONE;
    sSlaveUiMoveInfo.moves[3] = MOVE_NONE;
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

#ifdef REMOTE_OPPONENT_SLAVE
static bool32 Slave_PeekPacket(u8 *outFromId, const u8 **outData, u16 *outSize)
{
    u8 i;
    u8 status;

    if (sSlaveHasCachedPacket)
    {
        *outFromId = sSlaveCachedFromId;
        *outData = (const u8 *)sSlaveCachedPacket;
        *outSize = sSlaveCachedSize;
        return TRUE;
    }

    status = GetBlockReceivedStatus();
    if (status == 0)
        return FALSE;

    for (i = 0; i < MAX_LINK_PLAYERS; i++)
    {
        if ((status & (1 << i)) && i != GetMultiplayerId())
        {
            sSlaveCachedFromId = i;
            sSlaveCachedSize = BLOCK_BUFFER_SIZE;
            CpuCopy16(gBlockRecvBuffer[i], sSlaveCachedPacket, BLOCK_BUFFER_SIZE);
            ResetBlockReceivedFlag(i);
            sSlaveHasCachedPacket = TRUE;

            *outFromId = sSlaveCachedFromId;
            *outData = (const u8 *)sSlaveCachedPacket;
            *outSize = sSlaveCachedSize;
            return TRUE;
        }
    }

    return FALSE;
}

static void Slave_ConsumePeekedPacket(void)
{
    sSlaveHasCachedPacket = FALSE;
}
#endif

#ifdef REMOTE_OPPONENT_MASTER
static bool32 Master_PeekPacket(u8 *outFromId, const u8 **outData, u16 *outSize)
{
    u8 i;
    u8 status;

    if (sMasterHasCachedPacket)
    {
        *outFromId = sMasterCachedFromId;
        *outData = (const u8 *)sMasterCachedPacket;
        *outSize = sMasterCachedSize;
        return TRUE;
    }

    status = GetBlockReceivedStatus();
    if (status == 0)
        return FALSE;

    for (i = 0; i < MAX_LINK_PLAYERS; i++)
    {
        if ((status & (1 << i)) && i != GetMultiplayerId())
        {
            sMasterCachedFromId = i;
            sMasterCachedSize = BLOCK_BUFFER_SIZE;
            CpuCopy16(gBlockRecvBuffer[i], sMasterCachedPacket, BLOCK_BUFFER_SIZE);
            ResetBlockReceivedFlag(i);
            sMasterHasCachedPacket = TRUE;

            *outFromId = sMasterCachedFromId;
            *outData = (const u8 *)sMasterCachedPacket;
            *outSize = sMasterCachedSize;
            return TRUE;
        }
    }

    return FALSE;
}

static void Master_ConsumePeekedPacket(void)
{
    sMasterHasCachedPacket = FALSE;
}
#endif

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

bool32 RemoteOpponent_Master_SendActionRequest(
    u8 seq,
    u8 battlerId,
    const struct RemoteOpponentPartyInfo *partyInfo)
{
    // Backwards-compatible wrapper: no HUD info.
    struct RemoteOpponentMonInfo dummyMon;
    CpuFill16(0, &dummyMon, sizeof(dummyMon));
    return RemoteOpponent_Master_SendActionRequest2(seq, battlerId, &dummyMon, &dummyMon, partyInfo);
}

bool32 RemoteOpponent_Master_SendActionRequest2(
    u8 seq,
    u8 battlerId,
    const struct RemoteOpponentMonInfo *controlledMon,
    const struct RemoteOpponentMonInfo *targetMon,
    const struct RemoteOpponentPartyInfo *partyInfo)
{
    struct RemoteOppActionRequest req;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!IsLinkTaskFinished())
        return FALSE;

    req.type = REMOTE_OPP_MSG_REQUEST_ACTION;
    req.seq = seq;
    req.battlerId = battlerId;
    req.unused = 0;
    req.controlledMon = *controlledMon;
    req.targetMon = *targetMon;
    req.party = *partyInfo;

    return SendBlock(BitmaskAllOtherLinkPlayers(), &req, sizeof(req));
}

bool32 RemoteOpponent_Master_TryRecvActionChoice(u8 expectedSeq, u8 *outAction, u8 *outData)
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppActionResponse *resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    #ifdef REMOTE_OPPONENT_MASTER
    if (!Master_PeekPacket(&fromId, &data, &size))
        return FALSE;
    #else
    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;
    #endif

    resp = (const struct RemoteOppActionResponse *)data;
    if (resp->type != REMOTE_OPP_MSG_CHOOSE_ACTION)
        return FALSE;

    if (resp->seq != expectedSeq)
        return FALSE;

    *outAction = resp->action;
    *outData = resp->data;

    #ifdef REMOTE_OPPONENT_MASTER
    Master_ConsumePeekedPacket();
    #endif
    return TRUE;
}

bool32 RemoteOpponent_Master_TryRecvActionChoice2(u8 expectedSeq, u8 expectedBattlerId, u8 *outAction, u8 *outData)
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppActionResponse *resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

#ifdef REMOTE_OPPONENT_MASTER
    if (!Master_PeekPacket(&fromId, &data, &size))
        return FALSE;
#else
    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;
#endif

    resp = (const struct RemoteOppActionResponse *)data;
    if (resp->type != REMOTE_OPP_MSG_CHOOSE_ACTION)
        return FALSE;
    if (resp->battlerId != expectedBattlerId)
        return FALSE;
    if (resp->seq != expectedSeq)
    {
        // Stale response for this battler: consume+discard so it can't block the cache forever.
        // (Responses for other battlers are not consumed here; they may be needed elsewhere.)
#ifdef REMOTE_OPPONENT_MASTER
        Master_ConsumePeekedPacket();
#endif
        return FALSE;
    }

    *outAction = resp->action;
    *outData = resp->data;

#ifdef REMOTE_OPPONENT_MASTER
    Master_ConsumePeekedPacket();
#endif
    return TRUE;
}

bool32 RemoteOpponent_Master_SendMoveRequest(
    u8 seq,
    u8 battlerId,
    const struct RemoteOpponentMonInfo *controlledMon,
    const struct RemoteOpponentMonInfo *targetMon,
    const struct RemoteOpponentMoveInfo *moveInfo)
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
    req.controlledMon = *controlledMon;
    req.targetMon = *targetMon;
    req.moveInfo = *moveInfo;

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

    #ifdef REMOTE_OPPONENT_MASTER
    if (!Master_PeekPacket(&fromId, &data, &size))
        return FALSE;
    #else
    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;
    #endif

    resp = (const struct RemoteOppResponse *)data;
    if (resp->type != REMOTE_OPP_MSG_CHOOSE_MOVE)
        return FALSE;

    if (resp->seq != expectedSeq)
        return FALSE;

    *outMoveSlot = resp->moveSlot;

    #ifdef REMOTE_OPPONENT_MASTER
    Master_ConsumePeekedPacket();
    #endif
    return TRUE;
}

bool32 RemoteOpponent_Master_TryRecvMoveChoice2(u8 expectedSeq, u8 expectedBattlerId, u8 *outMoveSlot)
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppResponse *resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

#ifdef REMOTE_OPPONENT_MASTER
    if (!Master_PeekPacket(&fromId, &data, &size))
        return FALSE;
#else
    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;
#endif

    resp = (const struct RemoteOppResponse *)data;
    if (resp->type != REMOTE_OPP_MSG_CHOOSE_MOVE)
        return FALSE;
    if (resp->battlerId != expectedBattlerId)
        return FALSE;
    if (resp->seq != expectedSeq)
    {
        // Stale response for this battler: consume+discard so it can't block the cache forever.
#ifdef REMOTE_OPPONENT_MASTER
        Master_ConsumePeekedPacket();
#endif
        return FALSE;
    }

    *outMoveSlot = resp->moveSlot;

#ifdef REMOTE_OPPONENT_MASTER
    Master_ConsumePeekedPacket();
#endif
    return TRUE;
}

bool32 RemoteOpponent_Slave_TryRecvMoveRequest(
    u8 *outSeq,
    u8 *outBattlerId,
    struct RemoteOpponentMonInfo *outControlledMon,
    struct RemoteOpponentMonInfo *outTargetMon,
    struct RemoteOpponentMoveInfo *outMoveInfo)
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppRequest *req;

    if (!RemoteOpponent_IsReady())
        return FALSE;

#ifdef REMOTE_OPPONENT_SLAVE
    if (!Slave_PeekPacket(&fromId, &data, &size))
        return FALSE;
#else
    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;
#endif

    req = (const struct RemoteOppRequest *)data;
    if (req->type != REMOTE_OPP_MSG_REQUEST_MOVE)
        return FALSE;

    *outSeq = req->seq;
    *outBattlerId = req->battlerId;
    *outControlledMon = req->controlledMon;
    *outTargetMon = req->targetMon;
    *outMoveInfo = req->moveInfo;

#ifdef REMOTE_OPPONENT_SLAVE
    Slave_ConsumePeekedPacket();
#endif
    return TRUE;
}

bool32 RemoteOpponent_Slave_TryRecvActionRequest(
    u8 *outSeq,
    u8 *outBattlerId,
    struct RemoteOpponentPartyInfo *outPartyInfo)
{
    // Backwards-compatible wrapper: ignore HUD info.
    struct RemoteOpponentMonInfo controlledMon;
    struct RemoteOpponentMonInfo targetMon;
    return RemoteOpponent_Slave_TryRecvActionRequest2(outSeq, outBattlerId, &controlledMon, &targetMon, outPartyInfo);
}

bool32 RemoteOpponent_Slave_TryRecvActionRequest2(
    u8 *outSeq,
    u8 *outBattlerId,
    struct RemoteOpponentMonInfo *outControlledMon,
    struct RemoteOpponentMonInfo *outTargetMon,
    struct RemoteOpponentPartyInfo *outPartyInfo)
{
    u8 fromId;
    u16 size;
    const u8 *data;
    const struct RemoteOppActionRequest *req;

    if (!RemoteOpponent_IsReady())
        return FALSE;

#ifdef REMOTE_OPPONENT_SLAVE
    if (!Slave_PeekPacket(&fromId, &data, &size))
        return FALSE;
#else
    if (!TryRecvPacket(&fromId, &data, &size))
        return FALSE;
#endif

    req = (const struct RemoteOppActionRequest *)data;
    if (req->type != REMOTE_OPP_MSG_REQUEST_ACTION)
        return FALSE;

    *outSeq = req->seq;
    *outBattlerId = req->battlerId;
    *outControlledMon = req->controlledMon;
    *outTargetMon = req->targetMon;
    *outPartyInfo = req->party;

#ifdef REMOTE_OPPONENT_SLAVE
    Slave_ConsumePeekedPacket();
#endif
    return TRUE;
}

bool32 RemoteOpponent_Slave_SendMoveChoice(u8 seq, u8 moveSlot)
{
    return RemoteOpponent_Slave_SendMoveChoice2(seq, sSlavePendingBattlerId, moveSlot);
}

bool32 RemoteOpponent_Slave_SendMoveChoice2(u8 seq, u8 battlerId, u8 moveSlot)
{
    struct RemoteOppResponse resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!IsLinkTaskFinished())
        return FALSE;

    resp.type = REMOTE_OPP_MSG_CHOOSE_MOVE;
    resp.seq = seq;
    resp.battlerId = battlerId;
    resp.moveSlot = moveSlot;

    return SendBlock(BitmaskAllOtherLinkPlayers(), &resp, sizeof(resp));
}

bool32 RemoteOpponent_Slave_SendActionChoice(u8 seq, u8 action, u8 data)
{
    return RemoteOpponent_Slave_SendActionChoice2(seq, sSlavePendingBattlerId, action, data);
}

bool32 RemoteOpponent_Slave_SendActionChoice2(u8 seq, u8 battlerId, u8 action, u8 data)
{
    struct RemoteOppActionResponse resp;

    if (!RemoteOpponent_IsReady())
        return FALSE;

    if (!IsLinkTaskFinished())
        return FALSE;

    resp.type = REMOTE_OPP_MSG_CHOOSE_ACTION;
    resp.seq = seq;
    resp.battlerId = battlerId;
    resp.action = action;
    resp.data = data;
    resp.unused = 0;

    return SendBlock(BitmaskAllOtherLinkPlayers(), &resp, sizeof(resp));
}

void CB2_RemoteOpponentSlave(void)
{
    u8 seq;
    u8 battlerId;
    struct RemoteOpponentMonInfo controlledMon;
    struct RemoteOpponentMonInfo targetMon;
    struct RemoteOpponentMoveInfo moveInfo;
    struct RemoteOpponentPartyInfo partyInfo;
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
        if (uiStatus == SLAVE_UI_STATUS_PENDING)
        {
            if (sSlavePendingIsAction)
            {
                if (sSlaveActionSubscreen == SLAVE_ACTION_SUBSCREEN_PARTY)
                    SlaveUi_DrawParty();
                else
                    SlaveUi_DrawActionMenu();
            }
            else
            {
                SlaveUi_DrawMoves();
            }
        }
        else
        {
            SlaveUi_DrawStatus(uiStatus);
        }
    }

    // Accept new requests at any time; the latest request wins.
    if (RemoteOpponent_Slave_TryRecvActionRequest2(&seq, &battlerId, &controlledMon, &targetMon, &partyInfo))
    {
        sSlavePending = TRUE;
        sSlavePendingIsAction = TRUE;
        sSlavePendingSeq = seq;
        sSlavePendingBattlerId = battlerId;
        sSlaveActionCursor = 0;
        sSlaveActionSubscreen = SLAVE_ACTION_SUBSCREEN_MENU;
        sSlaveSelectedSlot = partyInfo.currentMonId;
        sSlaveUiControlledMon = controlledMon;
        sSlaveUiTargetMon = targetMon;
        sSlaveUiPartyInfo = partyInfo;
        SlaveUi_DrawActionMenu();
    }

    if (RemoteOpponent_Slave_TryRecvMoveRequest(&seq, &battlerId, &controlledMon, &targetMon, &moveInfo))
    {
        sSlavePending = TRUE;
        sSlavePendingIsAction = FALSE;
        sSlavePendingSeq = seq;
        sSlavePendingBattlerId = battlerId;
        sSlaveSelectedSlot = 0;

        sSlaveUiControlledMon = controlledMon;
        sSlaveUiTargetMon = targetMon;
        sSlaveUiMoveInfo = moveInfo;
        SlaveUi_DrawMoves();
    }

    if (!sSlavePending)
        return;

    if (sSlavePendingIsAction)
    {
        // Action UI is two-step:
        // 1) Pick FIGHT or SWITCH
        // 2) If SWITCH, pick party slot
        if (sSlaveActionSubscreen == SLAVE_ACTION_SUBSCREEN_MENU)
        {
            if (gMain.newKeys & (DPAD_UP | DPAD_DOWN))
            {
                sSlaveActionCursor ^= 1;
                SlaveUi_DrawActionMenu();
            }

            if (gMain.newKeys & A_BUTTON)
            {
                if (sSlaveActionCursor == 0)
                {
                    if (RemoteOpponent_Slave_SendActionChoice(sSlavePendingSeq, REMOTE_OPP_ACTION_FIGHT, 0))
                    {
                        sSlavePending = FALSE;
                        SlaveUi_DrawStatus(SLAVE_UI_STATUS_READY);
                    }
                }
                else
                {
                    sSlaveActionSubscreen = SLAVE_ACTION_SUBSCREEN_PARTY;
                    sSlaveUiLastSelectedSlot = 0xFF;
                    SlaveUi_DrawParty();
                }
            }

            // Intentionally do not handle B on this menu.
            // The prompt is coming from the master; cancelling locally desyncs UX.

            return;
        }
        else
        {
            if (gMain.newKeys & DPAD_UP)
            {
                if (sSlaveSelectedSlot > 0)
                    sSlaveSelectedSlot--;
            }
            else if (gMain.newKeys & DPAD_DOWN)
            {
                if (sSlaveSelectedSlot + 1 < PARTY_SIZE)
                    sSlaveSelectedSlot++;
            }

            if (sSlaveSelectedSlot != sSlaveUiLastSelectedSlot)
            {
                sSlaveUiLastSelectedSlot = sSlaveSelectedSlot;
                SlaveUi_DrawParty();
            }

            if (gMain.newKeys & A_BUTTON)
            {
                if (!SlaveUi_IsValidSwitchSlot(sSlaveSelectedSlot))
                    return;

                if (RemoteOpponent_Slave_SendActionChoice(sSlavePendingSeq, REMOTE_OPP_ACTION_SWITCH, sSlaveSelectedSlot))
                {
                    sSlavePending = FALSE;
                    SlaveUi_DrawStatus(SLAVE_UI_STATUS_READY);
                }
            }

            if (gMain.newKeys & B_BUTTON)
            {
                sSlaveActionSubscreen = SLAVE_ACTION_SUBSCREEN_MENU;
                SlaveUi_DrawActionMenu();
            }

            return;
        }
    }

    // Minimal, display-less UI:
    // Move UI:
    // - DPAD moves the cursor linearly (up/down)
    // - A selects
    // - B backs out to action menu (handled via REMOTE_OPP_MOVE_SLOT_CANCEL)
    if (gMain.newKeys & DPAD_UP)
    {
        u8 start = sSlaveSelectedSlot & 3;
        u8 i;

        // Find previous valid move; wrap to last if needed.
        for (i = 0; i < MAX_MON_MOVES; i++)
        {
            u8 candidate = (start + MAX_MON_MOVES - 1 - i) % MAX_MON_MOVES;
            if (sSlaveUiMoveInfo.moves[candidate] != MOVE_NONE)
            {
                sSlaveSelectedSlot = candidate;
                break;
            }
        }
    }
    else if (gMain.newKeys & DPAD_DOWN)
    {
        u8 start = sSlaveSelectedSlot & 3;
        u8 i;

        // Find next valid move; wrap to first if needed.
        for (i = 0; i < MAX_MON_MOVES; i++)
        {
            u8 candidate = (start + 1 + i) % MAX_MON_MOVES;
            if (sSlaveUiMoveInfo.moves[candidate] != MOVE_NONE)
            {
                sSlaveSelectedSlot = candidate;
                break;
            }
        }
    }

    if (sSlaveSelectedSlot != sSlaveUiLastSelectedSlot)
    {
        sSlaveUiLastSelectedSlot = sSlaveSelectedSlot;
        SlaveUi_DrawMoves();
    }

    if (gMain.newKeys & A_BUTTON)
    {
        if (RemoteOpponent_Slave_SendMoveChoice2(sSlavePendingSeq, sSlavePendingBattlerId, sSlaveSelectedSlot))
        {
            sSlavePending = FALSE;
            SlaveUi_DrawStatus(SLAVE_UI_STATUS_READY);
        }
    }

    if (gMain.newKeys & B_BUTTON)
    {
        // Mirror vanilla behavior: B cancels move selection and returns to the action menu.
        // We must inform the master so the battle engine can transition back.
        if (RemoteOpponent_Slave_SendMoveChoice2(sSlavePendingSeq, sSlavePendingBattlerId, REMOTE_OPP_MOVE_SLOT_CANCEL))
        {
            sSlavePending = FALSE;
            SlaveUi_DrawStatus(SLAVE_UI_STATUS_READY);
        }
    }
}

#endif // REMOTE_OPPONENT
