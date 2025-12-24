#ifndef GUARD_REMOTE_OPPONENT_H
#define GUARD_REMOTE_OPPONENT_H

#include "global.h"

// Define one of these at compile time:
// -DREMOTE_OPPONENT_LEADER   : normal game, but opponent moves can be chosen by a linked follower
// -DREMOTE_OPPONENT_FOLLOWER : boots into a minimal loop that only answers move/action requests

#if defined(REMOTE_OPPONENT_LEADER) || defined(REMOTE_OPPONENT_FOLLOWER)
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
	REMOTE_OPP_ACTION_ITEM = 2,
};

// Special move slot used by the follower to indicate "cancel/back" from the move menu.
// The leader translates this to the vanilla move-cancel return value (0xFFFF).
#define REMOTE_OPP_MOVE_SLOT_CANCEL 0xFF

// Call periodically (safe to call every frame). Opens a link (cable) the first time.
void RemoteOpponent_OpenLinkIfNeeded(void);

// True when 2+ players are connected and link player exchange is complete.
bool32 RemoteOpponent_IsReady(void);

// LEADER: request a move from the follower. Returns TRUE if the block send started.
bool32 RemoteOpponent_Leader_SendMoveRequest(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentMonInfo *controlledMon,
	u8 targetBattlerLeft,
	const struct RemoteOpponentMonInfo *targetMonLeft,
	u8 targetBattlerRight,
	const struct RemoteOpponentMonInfo *targetMonRight,
	const struct RemoteOpponentMoveInfo *moveInfo);

// LEADER: check for a move response. Returns TRUE when a valid response is received.
bool32 RemoteOpponent_Leader_TryRecvMoveChoice(u8 expectedSeq, u8 *outMoveSlot);

// LEADER: request an action (fight/switch) from the follower. Returns TRUE if the block send started.
bool32 RemoteOpponent_Leader_SendActionRequest(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentPartyInfo *partyInfo);

// LEADER: request an action (fight/switch) including minimal battle HUD info.
bool32 RemoteOpponent_Leader_SendActionRequest2(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentMonInfo *controlledMon,
	const struct RemoteOpponentMonInfo *targetMonLeft,
	const struct RemoteOpponentMonInfo *targetMonRight,
	const struct RemoteOpponentPartyInfo *partyInfo);

// LEADER: check for an action response. Returns TRUE when a valid response is received.
bool32 RemoteOpponent_Leader_TryRecvActionChoice(u8 expectedSeq, u8 *outAction, u8 *outData);

// FOLLOWER: check for a move request. Returns TRUE when a request is received.
bool32 RemoteOpponent_Follower_TryRecvMoveRequest(
	u8 *outSeq,
	u8 *outBattlerId,
	u8 *outTargetBattlerLeft,
	u8 *outTargetBattlerRight,
	struct RemoteOpponentMonInfo *outControlledMon,
	struct RemoteOpponentMonInfo *outTargetMonLeft,
	struct RemoteOpponentMonInfo *outTargetMonRight,
	struct RemoteOpponentMoveInfo *outMoveInfo);

// FOLLOWER: send selected move slot back to the leader.
bool32 RemoteOpponent_Follower_SendMoveChoice(u8 seq, u8 moveSlot, u8 targetBattlerId);

// FOLLOWER: check for an action request. Returns TRUE when a request is received.
bool32 RemoteOpponent_Follower_TryRecvActionRequest(
	u8 *outSeq,
	u8 *outBattlerId,
	struct RemoteOpponentPartyInfo *outPartyInfo);

// FOLLOWER: request variant that also outputs mon HUD info.
bool32 RemoteOpponent_Follower_TryRecvActionRequest2(
	u8 *outSeq,
	u8 *outBattlerId,
	struct RemoteOpponentMonInfo *outControlledMon,
	struct RemoteOpponentMonInfo *outTargetMonLeft,
	struct RemoteOpponentMonInfo *outTargetMonRight,
	struct RemoteOpponentPartyInfo *outPartyInfo);

// FOLLOWER: send selected action back to the leader.
bool32 RemoteOpponent_Follower_SendActionChoice(u8 seq, u8 action, u8 data);

// Variants that also include battlerId for routing (recommended).
bool32 RemoteOpponent_Leader_TryRecvMoveChoice2(u8 expectedSeq, u8 expectedBattlerId, u8 *outMoveSlot, u8 *outTargetBattlerId);
bool32 RemoteOpponent_Leader_TryRecvActionChoice2(u8 expectedSeq, u8 expectedBattlerId, u8 *outAction, u8 *outData);
bool32 RemoteOpponent_Follower_SendMoveChoice2(u8 seq, u8 battlerId, u8 moveSlot, u8 targetBattlerId);
bool32 RemoteOpponent_Follower_SendActionChoice2(u8 seq, u8 battlerId, u8 action, u8 data);

// FOLLOWER: main callback (boots into this if REMOTE_OPPONENT_FOLLOWER is set).
void CB2_InitRemoteOpponentFollower(void);
void CB2_RemoteOpponentFollower(void);

#endif // REMOTE_OPPONENT

#endif // GUARD_REMOTE_OPPONENT_H
