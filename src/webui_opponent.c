#include "global.h"

#ifdef WEBUI_OPPONENT

#include "webui_opponent.h"

// Place the mailbox in a fixed, zero-initialized EWRAM slot so the magic
// sentinel is set from boot (via the .bss init at RAM clear plus the explicit
// initializer below), and so the Lua bridge can find it without needing a
// battle to occur first.
EWRAM_DATA struct WebuiOpponentMailbox gWebuiOpponentMailbox = { .magic = WEBUI_OPP_MAGIC };

static void ZeroMailbox(void)
{
    u8 *p = (u8 *)&gWebuiOpponentMailbox;
    u32 i;
    for (i = 0; i < sizeof(gWebuiOpponentMailbox); i++)
        p[i] = 0;
}

void WebuiOpponent_Init(void)
{
    ZeroMailbox();
    gWebuiOpponentMailbox.magic = WEBUI_OPP_MAGIC;
    gWebuiOpponentMailbox.seq = 0;
    gWebuiOpponentMailbox.state = WEBUI_OPP_STATE_IDLE;
}

void WebuiOpponent_PostRequest(
    u8 battlerId,
    const struct WebuiOppMonInfo *controlledMon,
    u8 targetBattlerLeft,
    const struct WebuiOppMonInfo *targetMonLeft,
    u8 targetBattlerRight,
    const struct WebuiOppMonInfo *targetMonRight,
    const struct WebuiOppMoveInfo *moveInfo,
    const struct WebuiOppPartyInfo *partyInfo)
{
    if (gWebuiOpponentMailbox.magic != WEBUI_OPP_MAGIC)
        WebuiOpponent_Init();

    gWebuiOpponentMailbox.battlerId = battlerId;
    gWebuiOpponentMailbox.targetBattlerLeft = targetBattlerLeft;
    gWebuiOpponentMailbox.targetBattlerRight = targetBattlerRight;
    gWebuiOpponentMailbox.controlledMon = *controlledMon;
    gWebuiOpponentMailbox.targetMonLeft = *targetMonLeft;
    gWebuiOpponentMailbox.targetMonRight = *targetMonRight;
    gWebuiOpponentMailbox.moveInfo = *moveInfo;
    gWebuiOpponentMailbox.partyInfo = *partyInfo;

    gWebuiOpponentMailbox.action = 0;
    gWebuiOpponentMailbox.param1 = 0;
    gWebuiOpponentMailbox.param2 = 0;

    gWebuiOpponentMailbox.seq++;
    gWebuiOpponentMailbox.state = WEBUI_OPP_STATE_REQUEST;
}

bool32 WebuiOpponent_TryGetResponse(u8 *outAction, u8 *outParam1, u8 *outParam2)
{
    if (gWebuiOpponentMailbox.state != WEBUI_OPP_STATE_RESPONSE)
        return FALSE;

    if (outAction != NULL)
        *outAction = gWebuiOpponentMailbox.action;
    if (outParam1 != NULL)
        *outParam1 = gWebuiOpponentMailbox.param1;
    if (outParam2 != NULL)
        *outParam2 = gWebuiOpponentMailbox.param2;

    gWebuiOpponentMailbox.state = WEBUI_OPP_STATE_IDLE;
    return TRUE;
}

#endif // WEBUI_OPPONENT
