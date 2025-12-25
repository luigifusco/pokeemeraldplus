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

#include "data.h" // MAX_TRAINER_ITEMS

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
	// Special: used in doubles to back out from the partner's action selection.
	// The leader translates this to B_ACTION_CANCEL_PARTNER.
	REMOTE_OPP_ACTION_CANCEL_PARTNER = 3,
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

// LEADER: request a full decision from the follower (action + any required submenu input).
// The request includes all data needed to navigate menus locally: moves, party, and trainer items.
bool32 RemoteOpponent_Leader_SendDecisionRequest2(
	u8 seq,
	u8 battlerId,
	const struct RemoteOpponentMonInfo *controlledMon,
	u8 targetBattlerLeft,
	const struct RemoteOpponentMonInfo *targetMonLeft,
	u8 targetBattlerRight,
	const struct RemoteOpponentMonInfo *targetMonRight,
	const struct RemoteOpponentMoveInfo *moveInfo,
	const struct RemoteOpponentPartyInfo *partyInfo);

// LEADER: request full decisions for both opponents in a double battle.
// Allows the follower to pick actions/moves for both battlers locally with no intermediate link traffic.
bool32 RemoteOpponent_Leader_SendDecisionRequestDouble2(
	u8 seq,
	u8 battlerIdLeft,
	u8 battlerIdRight,
	const struct RemoteOpponentMonInfo *controlledMonLeft,
	const struct RemoteOpponentMonInfo *controlledMonRight,
	u8 targetBattlerLeft,
	const struct RemoteOpponentMonInfo *targetMonLeft,
	u8 targetBattlerRight,
	const struct RemoteOpponentMonInfo *targetMonRight,
	const struct RemoteOpponentMoveInfo *moveInfoLeft,
	const struct RemoteOpponentMoveInfo *moveInfoRight,
	const struct RemoteOpponentPartyInfo *partyInfo);

// LEADER: check for an action response. Returns TRUE when a valid response is received.
bool32 RemoteOpponent_Leader_TryRecvActionChoice(u8 expectedSeq, u8 *outAction, u8 *outData);

// LEADER: check for a decision response.
// For REMOTE_OPP_ACTION_FIGHT: outParam1 = moveSlot, outParam2 = targetBattlerId.
// For REMOTE_OPP_ACTION_SWITCH/ITEM: outParam1 = slot index, outParam2 unused.
bool32 RemoteOpponent_Leader_TryRecvDecisionChoice2(
	u8 expectedSeq,
	u8 expectedBattlerId,
	u8 *outAction,
	u8 *outParam1,
	u8 *outParam2);

// LEADER: check for a double-decision response.
bool32 RemoteOpponent_Leader_TryRecvDecisionChoiceDouble2(
	u8 expectedSeq,
	u8 expectedBattlerIdLeft,
	u8 expectedBattlerIdRight,
	u8 *outActionLeft,
	u8 *outParam1Left,
	u8 *outParam2Left,
	u8 *outActionRight,
	u8 *outParam1Right,
	u8 *outParam2Right);

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

// FOLLOWER: check for a decision request (includes moves + party + items).
bool32 RemoteOpponent_Follower_TryRecvDecisionRequest(
	u8 *outSeq,
	u8 *outBattlerId,
	u8 *outTargetBattlerLeft,
	u8 *outTargetBattlerRight,
	struct RemoteOpponentMonInfo *outControlledMon,
	struct RemoteOpponentMonInfo *outTargetMonLeft,
	struct RemoteOpponentMonInfo *outTargetMonRight,
	struct RemoteOpponentMoveInfo *outMoveInfo,
	struct RemoteOpponentPartyInfo *outPartyInfo,
	u16 outTrainerItems[MAX_TRAINER_ITEMS]);

// FOLLOWER: check for a double-decision request.
bool32 RemoteOpponent_Follower_TryRecvDecisionRequestDouble(
	u8 *outSeq,
	u8 *outBattlerIdLeft,
	u8 *outBattlerIdRight,
	u8 *outTargetBattlerLeft,
	u8 *outTargetBattlerRight,
	struct RemoteOpponentMonInfo *outControlledMonLeft,
	struct RemoteOpponentMonInfo *outControlledMonRight,
	struct RemoteOpponentMonInfo *outTargetMonLeft,
	struct RemoteOpponentMonInfo *outTargetMonRight,
	struct RemoteOpponentMoveInfo *outMoveInfoLeft,
	struct RemoteOpponentMoveInfo *outMoveInfoRight,
	struct RemoteOpponentPartyInfo *outPartyInfo,
	u16 outTrainerItems[MAX_TRAINER_ITEMS]);

// FOLLOWER: send final decision back to the leader.
bool32 RemoteOpponent_Follower_SendDecisionChoice2(
	u8 seq,
	u8 battlerId,
	u8 action,
	u8 param1,
	u8 param2);

// FOLLOWER: send final decisions for both opponents in a double battle.
bool32 RemoteOpponent_Follower_SendDecisionChoiceDouble2(
	u8 seq,
	u8 battlerIdLeft,
	u8 actionLeft,
	u8 param1Left,
	u8 param2Left,
	u8 battlerIdRight,
	u8 actionRight,
	u8 param1Right,
	u8 param2Right);

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
