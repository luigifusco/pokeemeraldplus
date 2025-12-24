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

// Call periodically (safe to call every frame). Opens a link (cable) the first time.
void RemoteOpponent_OpenLinkIfNeeded(void);

// True when 2+ players are connected and link player exchange is complete.
bool32 RemoteOpponent_IsReady(void);

// MASTER: request a move from the slave. Returns TRUE if the block send started.
bool32 RemoteOpponent_Master_SendMoveRequest(u8 seq, u8 battlerId, const u16 moves[4]);

// MASTER: check for a move response. Returns TRUE when a valid response is received.
bool32 RemoteOpponent_Master_TryRecvMoveChoice(u8 expectedSeq, u8 *outMoveSlot);

// SLAVE: check for a move request. Returns TRUE when a request is received.
bool32 RemoteOpponent_Slave_TryRecvMoveRequest(u8 *outSeq, u8 *outBattlerId, u16 outMoves[4]);

// SLAVE: send selected move slot back to the master.
bool32 RemoteOpponent_Slave_SendMoveChoice(u8 seq, u8 moveSlot);

// SLAVE: main callback (boots into this if REMOTE_OPPONENT_SLAVE is set).
void CB2_InitRemoteOpponentSlave(void);
void CB2_RemoteOpponentSlave(void);

#endif // REMOTE_OPPONENT

#endif // GUARD_REMOTE_OPPONENT_H
