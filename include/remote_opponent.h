#ifndef GUARD_REMOTE_OPPONENT_H
#define GUARD_REMOTE_OPPONENT_H

#include "global.h"

// Define one of these at compile time:
// -DREMOTE_OPPONENT_MASTER : normal game, but wild opponent moves can be chosen by a linked slave
// -DREMOTE_OPPONENT_SLAVE  : boots into a minimal loop that only answers move requests

#if defined(REMOTE_OPPONENT_MASTER) || defined(REMOTE_OPPONENT_SLAVE)
#define REMOTE_OPPONENT
#endif

#ifdef REMOTE_OPPONENT

struct RemoteOpponentMonInfo
{
	u16 species;
	u16 hp;
	u16 maxHp;
	u32 status1;
	u8 level;
	u8 nickname[POKEMON_NAME_LENGTH + 1];
};

struct RemoteOpponentMoveInfo
{
	u16 moves[MAX_MON_MOVES];
	u8 currentPp[MAX_MON_MOVES];
	u8 maxPp[MAX_MON_MOVES];
	u8 monTypes[2];
};

struct RemoteOpponentPartyInfo
{
	// Valid party slot range is [firstMonId, lastMonId).
	u8 firstMonId;
	u8 lastMonId;
	// Current active mon slots (for disallowing invalid switches).
	u8 currentMonId;
	u8 partnerMonId;
	struct RemoteOpponentMonInfo mons[PARTY_SIZE];
};

enum
{
	REMOTE_OPP_ACTION_FIGHT = 0,
	REMOTE_OPP_ACTION_SWITCH = 1,
};

// Special move slot used by the slave to indicate "cancel/back" from the move menu.
// The master translates this to the vanilla move-cancel return value (0xFFFF).
#define REMOTE_OPP_MOVE_SLOT_CANCEL 0xFF

// Call periodically (safe to call every frame). Opens a link (cable) the first time.
void RemoteOpponent_OpenLinkIfNeeded(void);

// True when 2+ players are connected and link player exchange is complete.
bool32 RemoteOpponent_IsReady(void);

// MASTER: request a move from the slave. Returns TRUE if the block send started.
bool32 RemoteOpponent_Master_SendMoveRequest(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentMonInfo *controlledMon,
	const struct RemoteOpponentMonInfo *targetMon,
	const struct RemoteOpponentMoveInfo *moveInfo);

// MASTER: check for a move response. Returns TRUE when a valid response is received.
bool32 RemoteOpponent_Master_TryRecvMoveChoice(u8 expectedSeq, u8 *outMoveSlot);

// MASTER: request an action (fight/switch) from the slave. Returns TRUE if the block send started.
bool32 RemoteOpponent_Master_SendActionRequest(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentPartyInfo *partyInfo);

// MASTER: request an action (fight/switch) including minimal battle HUD info.
bool32 RemoteOpponent_Master_SendActionRequest2(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentMonInfo *controlledMon,
	const struct RemoteOpponentMonInfo *targetMon,
	const struct RemoteOpponentPartyInfo *partyInfo);

// MASTER: check for an action response. Returns TRUE when a valid response is received.
bool32 RemoteOpponent_Master_TryRecvActionChoice(u8 expectedSeq, u8 *outAction, u8 *outData);

// SLAVE: check for a move request. Returns TRUE when a request is received.
bool32 RemoteOpponent_Slave_TryRecvMoveRequest(
	u8 *outSeq,
	u8 *outBattlerId,
	struct RemoteOpponentMonInfo *outControlledMon,
	struct RemoteOpponentMonInfo *outTargetMon,
	struct RemoteOpponentMoveInfo *outMoveInfo);

// SLAVE: send selected move slot back to the master.
bool32 RemoteOpponent_Slave_SendMoveChoice(u8 seq, u8 moveSlot);

// SLAVE: check for an action request. Returns TRUE when a request is received.
bool32 RemoteOpponent_Slave_TryRecvActionRequest(
	u8 *outSeq,
	u8 *outBattlerId,
	struct RemoteOpponentPartyInfo *outPartyInfo);

// SLAVE: request variant that also outputs mon HUD info.
bool32 RemoteOpponent_Slave_TryRecvActionRequest2(
	u8 *outSeq,
	u8 *outBattlerId,
	struct RemoteOpponentMonInfo *outControlledMon,
	struct RemoteOpponentMonInfo *outTargetMon,
	struct RemoteOpponentPartyInfo *outPartyInfo);

// SLAVE: send selected action back to the master.
bool32 RemoteOpponent_Slave_SendActionChoice(u8 seq, u8 action, u8 data);

// Variants that also include battlerId for routing (recommended).
bool32 RemoteOpponent_Master_TryRecvMoveChoice2(u8 expectedSeq, u8 expectedBattlerId, u8 *outMoveSlot);
bool32 RemoteOpponent_Master_TryRecvActionChoice2(u8 expectedSeq, u8 expectedBattlerId, u8 *outAction, u8 *outData);
bool32 RemoteOpponent_Slave_SendMoveChoice2(u8 seq, u8 battlerId, u8 moveSlot);
bool32 RemoteOpponent_Slave_SendActionChoice2(u8 seq, u8 battlerId, u8 action, u8 data);

// SLAVE: main callback (boots into this if REMOTE_OPPONENT_SLAVE is set).
void CB2_InitRemoteOpponentSlave(void);
void CB2_RemoteOpponentSlave(void);

#endif // REMOTE_OPPONENT

#endif // GUARD_REMOTE_OPPONENT_H
