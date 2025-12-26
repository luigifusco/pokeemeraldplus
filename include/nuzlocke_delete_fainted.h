#ifndef GUARD_NUZLOCKE_DELETE_FAINTED_H
#define GUARD_NUZLOCKE_DELETE_FAINTED_H

#include "global.h"

void Nuzlocke_ResetPendingFaintedDeletions(void);
void Nuzlocke_MarkBattlerFaintedForDeletion(u8 battler);
void Nuzlocke_TryDeletePendingAfterSendOut(u8 battler);

#endif // GUARD_NUZLOCKE_DELETE_FAINTED_H
