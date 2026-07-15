#include "global.h"
#include "battle.h"
#include "mail.h"
#include "main.h"
#include "overworld.h"
#include "party_menu.h"
#include "pokedex.h"
#include "pokemon.h"
#include "trainer_mon_swap.h"
#include "constants/items.h"

#ifdef SWAP_TRAINER_POKEMON

static EWRAM_DATA struct Pokemon sTrainerSwapEnemyParty[PARTY_SIZE] = {0};
static EWRAM_DATA struct Pokemon sTrainerSwapPlayerParty[PARTY_SIZE] = {0};
static u8 sTrainerSwapEnemyCount;
static u8 sTrainerSwapPlayerCount;
static u8 sTrainerSwapEnemySelection;
static u8 sTrainerSwapMenuSelection;
static bool8 sTrainerSwapPending;
static bool8 sTrainerSwapShowingEnemy;

static bool8 FieldCB2_StartTrainerMonSwap(void);
static void CB2_TrainerMonSwapReturnToEnemy(void);
static void CB2_TrainerMonSwapQuit(void);
static void ShowTrainerSwapEnemyParty(void);
static void ShowTrainerSwapPlayerParty(void);
static void CopyTrainerSwapPartyToPlayer(struct Pokemon *party, u8 count);
static void FinishTrainerMonSwap(void);

static void FullyHealSwapMon(struct Pokemon *mon)
{
    u8 i;
    u8 ppBonuses = GetMonData(mon, MON_DATA_PP_BONUSES);
    u16 hp = GetMonData(mon, MON_DATA_MAX_HP);
    u32 status = 0;

    SetMonData(mon, MON_DATA_HP, &hp);
    for (i = 0; i < MAX_MON_MOVES; i++)
    {
        u16 move = GetMonData(mon, MON_DATA_MOVE1 + i);
        u8 pp = CalculatePPWithBonus(move, ppBonuses, i);

        SetMonData(mon, MON_DATA_PP1 + i, &pp);
    }
    SetMonData(mon, MON_DATA_STATUS, &status);
}

bool8 ShouldOfferTrainerMonSwap(void)
{
    u32 excludedBattleTypes =
          BATTLE_TYPE_LINK
        | BATTLE_TYPE_RECORDED_LINK
        | BATTLE_TYPE_RECORDED
        | BATTLE_TYPE_FRONTIER
        | BATTLE_TYPE_TRAINER_HILL
        | BATTLE_TYPE_EREADER_TRAINER
        | BATTLE_TYPE_INGAME_PARTNER
        | BATTLE_TYPE_SECRET_BASE
        | BATTLE_TYPE_WALLY_TUTORIAL;

    return gBattleOutcome == B_OUTCOME_WON
        && (gBattleTypeFlags & BATTLE_TYPE_TRAINER)
        && !(gBattleTypeFlags & excludedBattleTypes);
}

void PrepareTrainerMonSwap(void)
{
    u8 i;

    sTrainerSwapPending = FALSE;
    sTrainerSwapPlayerCount = CalculatePlayerPartyCount();
    for (i = 0; i < PARTY_SIZE; i++)
    {
        CopyMon(
            &sTrainerSwapPlayerParty[i],
            &gPlayerParty[i],
            sizeof(struct Pokemon)
        );
    }

    sTrainerSwapEnemyCount = 0;
    for (i = 0; i < PARTY_SIZE; i++)
    {
        u16 species = GetMonData(&gEnemyParty[i], MON_DATA_SPECIES_OR_EGG);

        if (species == SPECIES_NONE || species == SPECIES_EGG)
            continue;
        CopyMon(
            &sTrainerSwapEnemyParty[sTrainerSwapEnemyCount],
            &gEnemyParty[i],
            sizeof(struct Pokemon)
        );
        FullyHealSwapMon(&sTrainerSwapEnemyParty[sTrainerSwapEnemyCount]);
        sTrainerSwapEnemyCount++;
    }

    if (sTrainerSwapEnemyCount != 0)
        sTrainerSwapPending = TRUE;
}

bool8 IsTrainerMonSwapPending(void)
{
    return sTrainerSwapPending;
}

void CB2_ReturnToFieldForTrainerMonSwap(void)
{
    gFieldCallback = NULL;
    gFieldCallback2 = FieldCB2_StartTrainerMonSwap;
    CB2_ReturnToField();
}

static bool8 FieldCB2_StartTrainerMonSwap(void)
{
    gFieldCallback2 = NULL;
    CleanupOverworldWindowsAndTilemaps();
    ShowTrainerSwapEnemyParty();
    return FALSE;
}

void SetTrainerMonSwapSelection(u8 slot)
{
    sTrainerSwapMenuSelection = slot;
}

void CB2_TrainerMonSwapSelectionMade(void)
{
    if (sTrainerSwapShowingEnemy)
    {
        if (sTrainerSwapMenuSelection >= sTrainerSwapEnemyCount)
        {
            ShowTrainerSwapEnemyParty();
            return;
        }
        sTrainerSwapEnemySelection = sTrainerSwapMenuSelection;
        ShowTrainerSwapPlayerParty();
        return;
    }

    if (sTrainerSwapMenuSelection < sTrainerSwapPlayerCount
        && sTrainerSwapEnemySelection < sTrainerSwapEnemyCount)
    {
        struct Pokemon incoming;
        u8 i;
        u8 mailId = GetMonData(
            &gPlayerParty[sTrainerSwapMenuSelection],
            MON_DATA_MAIL
        );
        u16 species;

        if (mailId != MAIL_NONE && mailId < MAIL_COUNT)
            ClearMail(&gSaveBlock1Ptr->mail[mailId]);

        CopyMon(
            &incoming,
            &sTrainerSwapEnemyParty[sTrainerSwapEnemySelection],
            sizeof(incoming)
        );
        SetMonOwnerToPlayer(&incoming);
        FullyHealSwapMon(&incoming);
        CopyMon(
            &gPlayerParty[sTrainerSwapMenuSelection],
            &incoming,
            sizeof(incoming)
        );

        species = GetMonData(&incoming, MON_DATA_SPECIES);
        GetSetPokedexFlag(SpeciesToNationalPokedexNum(species), FLAG_SET_SEEN);
        GetSetPokedexFlag(SpeciesToNationalPokedexNum(species), FLAG_SET_CAUGHT);
        CalculatePlayerPartyCount();
        sTrainerSwapPlayerCount = gPlayerPartyCount;
        for (i = 0; i < PARTY_SIZE; i++)
        {
            CopyMon(
                &sTrainerSwapPlayerParty[i],
                &gPlayerParty[i],
                sizeof(struct Pokemon)
            );
        }
    }

    FinishTrainerMonSwap();
}

static void ShowTrainerSwapEnemyParty(void)
{
    sTrainerSwapShowingEnemy = TRUE;
    CopyTrainerSwapPartyToPlayer(
        sTrainerSwapEnemyParty,
        sTrainerSwapEnemyCount
    );
    OpenTrainerMonSwapPartyMenu(TRUE, CB2_TrainerMonSwapQuit);
}

static void ShowTrainerSwapPlayerParty(void)
{
    sTrainerSwapShowingEnemy = FALSE;
    CopyTrainerSwapPartyToPlayer(
        sTrainerSwapPlayerParty,
        sTrainerSwapPlayerCount
    );
    OpenTrainerMonSwapPartyMenu(FALSE, CB2_TrainerMonSwapReturnToEnemy);
}

static void CopyTrainerSwapPartyToPlayer(struct Pokemon *party, u8 count)
{
    u8 i;

    ZeroPlayerPartyMons();
    for (i = 0; i < count; i++)
        CopyMon(&gPlayerParty[i], &party[i], sizeof(struct Pokemon));
    CalculatePlayerPartyCount();
}

static void CB2_TrainerMonSwapReturnToEnemy(void)
{
    ShowTrainerSwapEnemyParty();
}

static void CB2_TrainerMonSwapQuit(void)
{
    FinishTrainerMonSwap();
}

static void FinishTrainerMonSwap(void)
{
    CopyTrainerSwapPartyToPlayer(
        sTrainerSwapPlayerParty,
        sTrainerSwapPlayerCount
    );
    sTrainerSwapPending = FALSE;
    SetMainCallback2(CB2_ReturnToFieldContinueScriptPlayMapMusic);
}

#endif // SWAP_TRAINER_POKEMON
