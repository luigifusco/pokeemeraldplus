#include "global.h"
#include "battle.h"
#include "mail.h"
#include "main.h"
#include "pokedex.h"
#include "pokemon.h"
#include "pokemon_summary_screen.h"
#include "trainer_mon_swap.h"
#include "constants/items.h"

#ifdef SWAP_TRAINER_POKEMON

static MainCallback sReturnCallback;
static EWRAM_DATA struct Pokemon sTrainerSwapEnemyParty[PARTY_SIZE];
static u8 sTrainerSwapEnemyCount;
static u8 sTrainerSwapEnemySelection;

static void CB2_AfterTrainerSwapEnemySummary(void);
static void CB2_AfterTrainerSwapPlayerSummary(void);
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

void StartTrainerMonSwap(void)
{
    u8 i;

    sReturnCallback = gMain.savedCallback;
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

    if (sTrainerSwapEnemyCount == 0)
    {
        FinishTrainerMonSwap();
        return;
    }

    ShowPokemonSummaryScreen(
        SUMMARY_MODE_SELECT_MON,
        sTrainerSwapEnemyParty,
        0,
        sTrainerSwapEnemyCount - 1,
        CB2_AfterTrainerSwapEnemySummary
    );
}

static void CB2_AfterTrainerSwapEnemySummary(void)
{
    if (!gSummaryScreenSelectionMade)
    {
        FinishTrainerMonSwap();
        return;
    }

    sTrainerSwapEnemySelection = gLastViewedMonIndex;
    CalculatePlayerPartyCount();
    if (gPlayerPartyCount == 0)
    {
        FinishTrainerMonSwap();
        return;
    }

    ShowPokemonSummaryScreen(
        SUMMARY_MODE_SELECT_MON,
        gPlayerParty,
        0,
        gPlayerPartyCount - 1,
        CB2_AfterTrainerSwapPlayerSummary
    );
}

static void CB2_AfterTrainerSwapPlayerSummary(void)
{
    if (gSummaryScreenSelectionMade
        && gLastViewedMonIndex < gPlayerPartyCount
        && sTrainerSwapEnemySelection < sTrainerSwapEnemyCount)
    {
        struct Pokemon incoming;
        u8 mailId = GetMonData(&gPlayerParty[gLastViewedMonIndex], MON_DATA_MAIL);
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
        CopyMon(&gPlayerParty[gLastViewedMonIndex], &incoming, sizeof(incoming));

        species = GetMonData(&incoming, MON_DATA_SPECIES);
        GetSetPokedexFlag(SpeciesToNationalPokedexNum(species), FLAG_SET_SEEN);
        GetSetPokedexFlag(SpeciesToNationalPokedexNum(species), FLAG_SET_CAUGHT);
        CalculatePlayerPartyCount();
    }

    FinishTrainerMonSwap();
}

static void FinishTrainerMonSwap(void)
{
    SetMainCallback2(sReturnCallback);
}

#endif // SWAP_TRAINER_POKEMON
