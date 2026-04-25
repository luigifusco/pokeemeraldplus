#ifndef GUARD_WEBUI_OPPONENT_H
#define GUARD_WEBUI_OPPONENT_H

#ifdef WEBUI_OPPONENT

#include "global.h"
#include "battle.h"
#include "data.h" // MAX_TRAINER_ITEMS

struct WebuiOppMonInfo
{
    u16 species;
    u16 hp;
    u16 maxHp;
    u32 status1;
    u8 level;
    u8 nickname[POKEMON_NAME_LENGTH + 1];
};

struct WebuiOppMoveInfo
{
    u16 moves[MAX_MON_MOVES];
    u8 currentPp[MAX_MON_MOVES];
    u8 maxPp[MAX_MON_MOVES];
    u8 monTypes[2];
};

struct WebuiOppPartyInfo
{
    // Valid party slot range is [firstMonId, lastMonId).
    u8 firstMonId;
    u8 lastMonId;
    // Current active mon slots (for disallowing invalid switches).
    u8 currentMonId;
    u8 partnerMonId;
    struct WebuiOppMonInfo mons[PARTY_SIZE];
};

enum
{
    WEBUI_OPP_ACTION_FIGHT = 0,
    WEBUI_OPP_ACTION_SWITCH = 1,
    WEBUI_OPP_ACTION_ITEM = 2,
    WEBUI_OPP_ACTION_CANCEL_PARTNER = 3,
    WEBUI_OPP_ACTION_AUTO = 4,
};

enum
{
    WEBUI_OPP_STATE_IDLE = 0,
    WEBUI_OPP_STATE_REQUEST = 1,
    WEBUI_OPP_STATE_RESPONSE = 2,
};

// ASCII 'WUIO' in little-endian memory order.
#define WEBUI_OPP_MAGIC 0x4F495557

struct WebuiOpponentMailbox
{
    u32 magic;
    u8  seq;
    u8  state;
    u8  battlerId;
    u8  action;              // response
    u8  param1;              // response (moveSlot | partySlot | itemSlot)
    u8  param2;              // response (targetBattlerId for FIGHT)
    u8  targetBattlerLeft;
    u8  targetBattlerRight;
    struct WebuiOppMonInfo   controlledMon;
    struct WebuiOppMonInfo   targetMonLeft;
    struct WebuiOppMonInfo   targetMonRight;
    struct WebuiOppMoveInfo  moveInfo;
    struct WebuiOppPartyInfo partyInfo;
    u16 trainerItems[MAX_TRAINER_ITEMS];
};

extern struct WebuiOpponentMailbox gWebuiOpponentMailbox;

void WebuiOpponent_Init(void);
void WebuiOpponent_PostRequest(
    u8 battlerId,
    const struct WebuiOppMonInfo *controlledMon,
    u8 targetBattlerLeft,
    const struct WebuiOppMonInfo *targetMonLeft,
    u8 targetBattlerRight,
    const struct WebuiOppMonInfo *targetMonRight,
    const struct WebuiOppMoveInfo *moveInfo,
    const struct WebuiOppPartyInfo *partyInfo);
bool32 WebuiOpponent_TryGetResponse(u8 *outAction, u8 *outParam1, u8 *outParam2);

#endif // WEBUI_OPPONENT

#endif // GUARD_WEBUI_OPPONENT_H
