#include "global.h"
#include "battle.h"
#include "battle_anim.h"
#include "battle_util.h"
#include "party_menu.h"
#include "pokemon.h"
#include "pokemon_storage_system.h"
#include "constants/species.h"

#ifdef NUZLOCKE_DELETE_FAINTED

static u8 sPendingDeletionPartyIndex[MAX_BATTLERS_COUNT];

static bool8 Nuzlocke_ShouldApply(void)
{
    // Party index compaction is risky in battle types that have different party routing.
    // Keep this feature limited to standard single-player battles.
    if (gBattleTypeFlags & (BATTLE_TYPE_LINK
                            | BATTLE_TYPE_RECORDED
                            | BATTLE_TYPE_RECORDED_LINK
                            | BATTLE_TYPE_MULTI
                            | BATTLE_TYPE_INGAME_PARTNER
                            | BATTLE_TYPE_SAFARI
                            | BATTLE_TYPE_TRAINER_HILL
                            | BATTLE_TYPE_FRONTIER))
        return FALSE;

    return TRUE;
}

static void AdjustPartyIndexAfterDeletion8(u8 *index, u8 deletedPartyIndex)
{
    if (*index != PARTY_SIZE && *index > deletedPartyIndex)
        (*index)--;
}

static void AdjustPartyIndexAfterDeletion16(u16 *index, u8 deletedPartyIndex)
{
    if (*index != PARTY_SIZE && *index > deletedPartyIndex)
        (*index)--;
}

static void AdjustGivenExpMonsAfterDeletion(u8 deletedPartyIndex)
{
    u8 oldMask = gBattleStruct->givenExpMons;
    u8 newMask = 0;
    s32 i;

    for (i = 0; i < PARTY_SIZE; i++)
    {
        if (i == deletedPartyIndex)
            continue;

        if (oldMask & (1 << i))
        {
            u8 newIndex = i;
            if (i > deletedPartyIndex)
                newIndex--;
            newMask |= (1 << newIndex);
        }
    }

    gBattleStruct->givenExpMons = newMask;
}

void Nuzlocke_ResetPendingFaintedDeletions(void)
{
    s32 i;

    for (i = 0; i < MAX_BATTLERS_COUNT; i++)
        sPendingDeletionPartyIndex[i] = PARTY_SIZE;
}

void Nuzlocke_MarkBattlerFaintedForDeletion(u8 battler)
{
    u8 partyIndex;

    if (!Nuzlocke_ShouldApply())
        return;

    if (GetBattlerSide(battler) != B_SIDE_PLAYER)
        return;

    partyIndex = gBattlerPartyIndexes[battler];
    if (partyIndex >= PARTY_SIZE)
        return;

    if (GetMonData(&gPlayerParty[partyIndex], MON_DATA_SPECIES) == SPECIES_NONE)
        return;

    sPendingDeletionPartyIndex[battler] = partyIndex;
}

void Nuzlocke_TryDeletePendingAfterSendOut(u8 battler)
{
    u8 deletedPartyIndex;
    s32 i;

    if (!Nuzlocke_ShouldApply())
        return;

    if (GetBattlerSide(battler) != B_SIDE_PLAYER)
        return;

    deletedPartyIndex = sPendingDeletionPartyIndex[battler];
    if (deletedPartyIndex >= PARTY_SIZE)
        return;

    // If the battler hasn't actually switched in yet, wait.
    if (gBattlerPartyIndexes[battler] == deletedPartyIndex)
        return;

    // Sanity: only delete if the mon still exists and is fainted.
    if (GetMonData(&gPlayerParty[deletedPartyIndex], MON_DATA_SPECIES) == SPECIES_NONE
     || GetMonData(&gPlayerParty[deletedPartyIndex], MON_DATA_HP) != 0)
    {
        sPendingDeletionPartyIndex[battler] = PARTY_SIZE;
        return;
    }

    ZeroMonData(&gPlayerParty[deletedPartyIndex]);
    CompactPartySlots();

    // Fix up all indices that refer to party slots after compaction.
    for (i = 0; i < gBattlersCount; i++)
    {
        if (GetBattlerSide(i) == B_SIDE_PLAYER)
        {
            AdjustPartyIndexAfterDeletion16(&gBattlerPartyIndexes[i], deletedPartyIndex);
            if (gBattleStruct->battlerPartyIndexes[i] != PARTY_SIZE
                && gBattleStruct->battlerPartyIndexes[i] > deletedPartyIndex)
                gBattleStruct->battlerPartyIndexes[i]--;

            if (gBattleStruct->monToSwitchIntoId[i] != PARTY_SIZE)
            {
                if (gBattleStruct->monToSwitchIntoId[i] > deletedPartyIndex)
                    gBattleStruct->monToSwitchIntoId[i]--;
            }
        }
    }

    for (i = 0; i < MAX_BATTLERS_COUNT; i++)
        AdjustPartyIndexAfterDeletion8(&sPendingDeletionPartyIndex[i], deletedPartyIndex);

    AdjustGivenExpMonsAfterDeletion(deletedPartyIndex);

    // Clear for this battler now that the deletion has been applied.
    sPendingDeletionPartyIndex[battler] = PARTY_SIZE;

    // Refresh party order buffers used by the party menu for future switches.
    if (!(gBattleTypeFlags & BATTLE_TYPE_MULTI))
    {
        for (i = 0; i < gBattlersCount; i++)
            BufferBattlePartyCurrentOrderBySide(i, 0);
    }
}

#else

void Nuzlocke_ResetPendingFaintedDeletions(void)
{
}

void Nuzlocke_MarkBattlerFaintedForDeletion(u8 battler)
{
    (void)battler;
}

void Nuzlocke_TryDeletePendingAfterSendOut(u8 battler)
{
    (void)battler;
}

#endif
