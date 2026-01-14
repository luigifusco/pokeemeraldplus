#include "global.h"
#include "battle.h"
#include "battle_ai_switch_items.h"
#include "battle_ai_script_commands.h"
#include "battle_anim.h"
#include "battle_arena.h"
#include "battle_controllers.h"
#include "battle_message.h"
#include "battle_interface.h"
#include "battle_setup.h"
#include "battle_tower.h"
#include "battle_tv.h"
#include "bg.h"
#include "data.h"
#include "frontier_util.h"
#include "item.h"
#include "link.h"
#include "main.h"
#include "m4a.h"
#include "palette.h"
#include "remote_opponent.h"
#include "pokeball.h"
#include "pokemon.h"
#include "random.h"
#include "reshow_battle_screen.h"
#include "sound.h"
#include "string_util.h"
#include "task.h"
#include "text.h"
#include "util.h"
#include "window.h"
#include "constants/battle_anim.h"
#include "constants/item_effects.h"
#include "constants/items.h"
#include "constants/moves.h"
#include "constants/songs.h"
#include "constants/trainers.h"
#include "trainer_hill.h"

static u8 GetRemoteOppAiItemType(u16 itemId, const u8 *itemEffect)
{
    if (itemId == ITEM_FULL_RESTORE)
        return AI_ITEM_FULL_RESTORE;
    else if (itemEffect != NULL && (itemEffect[4] & ITEM4_HEAL_HP))
        return AI_ITEM_HEAL_HP;
    else if (itemEffect != NULL && (itemEffect[3] & ITEM3_STATUS_ALL))
        return AI_ITEM_CURE_CONDITION;
    else if (itemEffect != NULL && ((itemEffect[0] & (ITEM0_DIRE_HIT | ITEM0_X_ATTACK)) || itemEffect[1] != 0 || itemEffect[2] != 0))
        return AI_ITEM_X_STAT;
    else if (itemEffect != NULL && (itemEffect[3] & ITEM3_GUARD_SPEC))
        return AI_ITEM_GUARD_SPEC;
    else
        return AI_ITEM_NOT_RECOGNIZABLE;
}

static u8 GetRemoteOppAiHealFlags(u16 itemId, const u8 *itemEffect, u8 battler)
{
    u8 flags = 0;

    if (itemEffect == NULL)
        return 0;

    // Mirror the AI's bitfield usage in battle_ai_switch_items.c.
    if ((itemEffect[3] & ITEM3_SLEEP) && (gBattleMons[battler].status1 & STATUS1_SLEEP))
        flags |= (1 << AI_HEAL_SLEEP);
    if ((itemEffect[3] & ITEM3_POISON) && (gBattleMons[battler].status1 & (STATUS1_POISON | STATUS1_TOXIC_POISON)))
        flags |= (1 << AI_HEAL_POISON);
    if ((itemEffect[3] & ITEM3_BURN) && (gBattleMons[battler].status1 & STATUS1_BURN))
        flags |= (1 << AI_HEAL_BURN);
    if ((itemEffect[3] & ITEM3_FREEZE) && (gBattleMons[battler].status1 & STATUS1_FREEZE))
        flags |= (1 << AI_HEAL_FREEZE);
    if ((itemEffect[3] & ITEM3_PARALYSIS) && (gBattleMons[battler].status1 & STATUS1_PARALYSIS))
        flags |= (1 << AI_HEAL_PARALYSIS);
    if ((itemEffect[3] & ITEM3_CONFUSION) && (gBattleMons[battler].status2 & STATUS2_CONFUSION))
        flags |= (1 << AI_HEAL_CONFUSION);

    // FULL RESTORE also cures status.
    if (itemId == ITEM_FULL_RESTORE && (gBattleMons[battler].status1 || (gBattleMons[battler].status2 & STATUS2_CONFUSION)))
    {
        if (gBattleMons[battler].status1 & STATUS1_SLEEP)
            flags |= (1 << AI_HEAL_SLEEP);
        else if (gBattleMons[battler].status1 & (STATUS1_POISON | STATUS1_TOXIC_POISON))
            flags |= (1 << AI_HEAL_POISON);
        else if (gBattleMons[battler].status1 & STATUS1_BURN)
            flags |= (1 << AI_HEAL_BURN);
        else if (gBattleMons[battler].status1 & STATUS1_FREEZE)
            flags |= (1 << AI_HEAL_FREEZE);
        else if (gBattleMons[battler].status1 & STATUS1_PARALYSIS)
            flags |= (1 << AI_HEAL_PARALYSIS);
        else if (gBattleMons[battler].status2 & STATUS2_CONFUSION)
            flags |= (1 << AI_HEAL_CONFUSION);
    }

    return flags;
}

static u8 GetRemoteOppAiXStatFlags(const u8 *itemEffect)
{
    u8 flags = 0;

    if (itemEffect == NULL)
        return 0;

    if (itemEffect[0] & ITEM0_X_ATTACK)
        flags |= (1 << AI_X_ATTACK);
    if (itemEffect[1] & ITEM1_X_DEFEND)
        flags |= (1 << AI_X_DEFEND);
    if (itemEffect[1] & ITEM1_X_SPEED)
        flags |= (1 << AI_X_SPEED);
    if (itemEffect[2] & ITEM2_X_SPATK)
        flags |= (1 << AI_X_SPATK);
    if (itemEffect[2] & ITEM2_X_ACCURACY)
        flags |= (1 << AI_X_ACCURACY);
    if (itemEffect[0] & ITEM0_DIRE_HIT)
        flags |= (1 << AI_DIRE_HIT);

    return flags;
}

static void OpponentHandleGetMonData(void);
static void OpponentHandleGetRawMonData(void);
static void OpponentHandleSetMonData(void);
static void OpponentHandleSetRawMonData(void);
static void OpponentHandleLoadMonSprite(void);
static void OpponentHandleSwitchInAnim(void);
static void OpponentHandleReturnMonToBall(void);
static void OpponentHandleDrawTrainerPic(void);
static void OpponentHandleTrainerSlide(void);
static void OpponentHandleTrainerSlideBack(void);
static void OpponentHandleFaintAnimation(void);
static void OpponentHandlePaletteFade(void);
static void OpponentHandleSuccessBallThrowAnim(void);
static void OpponentHandleBallThrow(void);
static void OpponentHandlePause(void);
static void OpponentHandleMoveAnimation(void);
static void OpponentHandlePrintString(void);
static void OpponentHandlePrintSelectionString(void);
static void OpponentHandleChooseAction(void);
static void OpponentHandleYesNoBox(void);
static void OpponentHandleChooseMove(void);
#ifdef REMOTE_OPPONENT_LEADER
static void OpponentHandleChooseAction_RemoteWait(void);
static void OpponentHandleChooseAction_RemoteWaitBundledPartner(void);
static void OpponentHandleChooseMove_RemoteWait(void);
#endif
static void OpponentHandleChooseItem(void);
static void OpponentHandleChoosePokemon(void);
static void OpponentHandleCmd23(void);
static void OpponentHandleHealthBarUpdate(void);
static void OpponentHandleExpUpdate(void);
static void OpponentHandleStatusIconUpdate(void);
static void OpponentHandleStatusAnimation(void);
static void OpponentHandleStatusXor(void);
static void OpponentHandleDataTransfer(void);
static void OpponentHandleDMA3Transfer(void);
static void OpponentHandlePlayBGM(void);
static void OpponentHandleCmd32(void);
static void OpponentHandleTwoReturnValues(void);
static void OpponentHandleChosenMonReturnValue(void);
static void OpponentHandleOneReturnValue(void);
static void OpponentHandleOneReturnValue_Duplicate(void);
static void OpponentHandleClearUnkVar(void);
static void OpponentHandleSetUnkVar(void);
static void OpponentHandleClearUnkFlag(void);
static void OpponentHandleToggleUnkFlag(void);
static void OpponentHandleHitAnimation(void);
static void OpponentHandleCantSwitch(void);
static void OpponentHandlePlaySE(void);

#ifdef REMOTE_OPPONENT_LEADER
struct RemoteOppWaitState
{
    u8 expectedSeq;
    bool8 requestSent;
    // For bundled doubles decision requests: 0 = nothing sent, 1 = left sent, 2 = both sent.
    u8 bundledSendStage;
    u16 connectTimeout;
    u16 responseTimeout;
    u32 lastVBlank;
};

// These are fairly large, and IWRAM is extremely tight in Emerald.
// Keep them in EWRAM so the IWRAM stack has enough space to boot.
static EWRAM_DATA u8 sRemoteOppSeq = 0;
static EWRAM_DATA struct RemoteOppWaitState sRemoteOppMoveState[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOppWaitState sRemoteOppActionState[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOpponentMonInfo sRemoteOppControlledMon[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOpponentMonInfo sRemoteOppTargetMon[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOpponentMonInfo sRemoteOppTargetMonLeft[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOpponentMonInfo sRemoteOppTargetMonRight[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppTargetBattlerLeft[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppTargetBattlerRight[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOpponentMoveInfo sRemoteOppMoveInfo[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA bool8 sRemoteOppHasPendingDecision[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppPendingDecisionAction[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppPendingDecisionParam1[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppPendingDecisionParam2[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA bool8 sRemoteOppHasPendingMoveDecision[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppPendingMoveSeq[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppPendingMoveSlot[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA u8 sRemoteOppPendingTargetBattler[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA struct RemoteOpponentPartyInfo sRemoteOppParty[MAX_BATTLERS_COUNT] = {0};
static EWRAM_DATA bool8 sRemoteOppFallbackToAI[MAX_BATTLERS_COUNT] = {0};
#endif
static void OpponentHandlePlayFanfareOrBGM(void);
static void OpponentHandleFaintingCry(void);
static void OpponentHandleIntroSlide(void);
static void OpponentHandleIntroTrainerBallThrow(void);
static void OpponentHandleDrawPartyStatusSummary(void);
static void OpponentHandleHidePartyStatusSummary(void);
static void OpponentHandleEndBounceEffect(void);
static void OpponentHandleSpriteInvisibility(void);
static void OpponentHandleBattleAnimation(void);
static void OpponentHandleLinkStandbyMsg(void);
static void OpponentHandleResetActionMoveSelection(void);
static void OpponentHandleEndLinkBattle(void);
static void OpponentCmdEnd(void);

static void OpponentBufferRunCommand(void);
static void OpponentBufferExecCompleted(void);
static void SwitchIn_HandleSoundAndEnd(void);
static u32 GetOpponentMonData(u8 monId, u8 *dst);
static void SetOpponentMonData(u8 monId);
static void StartSendOutAnim(u8 battler, bool8 dontClearSubstituteBit);
static void DoSwitchOutAnimation(void);
static void OpponentDoMoveAnimation(void);
static void SpriteCB_FreeOpponentSprite(struct Sprite *sprite);
static void Task_StartSendOutAnim(u8 taskId);
static void EndDrawPartyStatusSummary(void);

static void (*const sOpponentBufferCommands[CONTROLLER_CMDS_COUNT])(void) =
{
    [CONTROLLER_GETMONDATA]               = OpponentHandleGetMonData,
    [CONTROLLER_GETRAWMONDATA]            = OpponentHandleGetRawMonData,
    [CONTROLLER_SETMONDATA]               = OpponentHandleSetMonData,
    [CONTROLLER_SETRAWMONDATA]            = OpponentHandleSetRawMonData,
    [CONTROLLER_LOADMONSPRITE]            = OpponentHandleLoadMonSprite,
    [CONTROLLER_SWITCHINANIM]             = OpponentHandleSwitchInAnim,
    [CONTROLLER_RETURNMONTOBALL]          = OpponentHandleReturnMonToBall,
    [CONTROLLER_DRAWTRAINERPIC]           = OpponentHandleDrawTrainerPic,
    [CONTROLLER_TRAINERSLIDE]             = OpponentHandleTrainerSlide,
    [CONTROLLER_TRAINERSLIDEBACK]         = OpponentHandleTrainerSlideBack,
    [CONTROLLER_FAINTANIMATION]           = OpponentHandleFaintAnimation,
    [CONTROLLER_PALETTEFADE]              = OpponentHandlePaletteFade,
    [CONTROLLER_SUCCESSBALLTHROWANIM]     = OpponentHandleSuccessBallThrowAnim,
    [CONTROLLER_BALLTHROWANIM]            = OpponentHandleBallThrow,
    [CONTROLLER_PAUSE]                    = OpponentHandlePause,
    [CONTROLLER_MOVEANIMATION]            = OpponentHandleMoveAnimation,
    [CONTROLLER_PRINTSTRING]              = OpponentHandlePrintString,
    [CONTROLLER_PRINTSTRINGPLAYERONLY]    = OpponentHandlePrintSelectionString,
    [CONTROLLER_CHOOSEACTION]             = OpponentHandleChooseAction,
    [CONTROLLER_YESNOBOX]                 = OpponentHandleYesNoBox,
    [CONTROLLER_CHOOSEMOVE]               = OpponentHandleChooseMove,
    [CONTROLLER_OPENBAG]                  = OpponentHandleChooseItem,
    [CONTROLLER_CHOOSEPOKEMON]            = OpponentHandleChoosePokemon,
    [CONTROLLER_23]                       = OpponentHandleCmd23,
    [CONTROLLER_HEALTHBARUPDATE]          = OpponentHandleHealthBarUpdate,
    [CONTROLLER_EXPUPDATE]                = OpponentHandleExpUpdate,
    [CONTROLLER_STATUSICONUPDATE]         = OpponentHandleStatusIconUpdate,
    [CONTROLLER_STATUSANIMATION]          = OpponentHandleStatusAnimation,
    [CONTROLLER_STATUSXOR]                = OpponentHandleStatusXor,
    [CONTROLLER_DATATRANSFER]             = OpponentHandleDataTransfer,
    [CONTROLLER_DMA3TRANSFER]             = OpponentHandleDMA3Transfer,
    [CONTROLLER_PLAYBGM]                  = OpponentHandlePlayBGM,
    [CONTROLLER_32]                       = OpponentHandleCmd32,
    [CONTROLLER_TWORETURNVALUES]          = OpponentHandleTwoReturnValues,
    [CONTROLLER_CHOSENMONRETURNVALUE]     = OpponentHandleChosenMonReturnValue,
    [CONTROLLER_ONERETURNVALUE]           = OpponentHandleOneReturnValue,
    [CONTROLLER_ONERETURNVALUE_DUPLICATE] = OpponentHandleOneReturnValue_Duplicate,
    [CONTROLLER_CLEARUNKVAR]              = OpponentHandleClearUnkVar,
    [CONTROLLER_SETUNKVAR]                = OpponentHandleSetUnkVar,
    [CONTROLLER_CLEARUNKFLAG]             = OpponentHandleClearUnkFlag,
    [CONTROLLER_TOGGLEUNKFLAG]            = OpponentHandleToggleUnkFlag,
    [CONTROLLER_HITANIMATION]             = OpponentHandleHitAnimation,
    [CONTROLLER_CANTSWITCH]               = OpponentHandleCantSwitch,
    [CONTROLLER_PLAYSE]                   = OpponentHandlePlaySE,
    [CONTROLLER_PLAYFANFAREORBGM]         = OpponentHandlePlayFanfareOrBGM,
    [CONTROLLER_FAINTINGCRY]              = OpponentHandleFaintingCry,
    [CONTROLLER_INTROSLIDE]               = OpponentHandleIntroSlide,
    [CONTROLLER_INTROTRAINERBALLTHROW]    = OpponentHandleIntroTrainerBallThrow,
    [CONTROLLER_DRAWPARTYSTATUSSUMMARY]   = OpponentHandleDrawPartyStatusSummary,
    [CONTROLLER_HIDEPARTYSTATUSSUMMARY]   = OpponentHandleHidePartyStatusSummary,
    [CONTROLLER_ENDBOUNCE]                = OpponentHandleEndBounceEffect,
    [CONTROLLER_SPRITEINVISIBILITY]       = OpponentHandleSpriteInvisibility,
    [CONTROLLER_BATTLEANIMATION]          = OpponentHandleBattleAnimation,
    [CONTROLLER_LINKSTANDBYMSG]           = OpponentHandleLinkStandbyMsg,
    [CONTROLLER_RESETACTIONMOVESELECTION] = OpponentHandleResetActionMoveSelection,
    [CONTROLLER_ENDLINKBATTLE]            = OpponentHandleEndLinkBattle,
    [CONTROLLER_TERMINATOR_NOP]           = OpponentCmdEnd
};

// unknown unused data
static const u8 sUnused[] = {0xB0, 0xB0, 0xC8, 0x98, 0x28, 0x28, 0x28, 0x20};

static void OpponentDummy(void)
{
}

void SetControllerToOpponent(void)
{
    gBattlerControllerFuncs[gActiveBattler] = OpponentBufferRunCommand;
}

static void OpponentBufferRunCommand(void)
{
    if (gBattleControllerExecFlags & gBitTable[gActiveBattler])
    {
        if (gBattleBufferA[gActiveBattler][0] < ARRAY_COUNT(sOpponentBufferCommands))
            sOpponentBufferCommands[gBattleBufferA[gActiveBattler][0]]();
        else
            OpponentBufferExecCompleted();
    }
}

static void CompleteOnBattlerSpriteCallbackDummy(void)
{
    if (gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
        OpponentBufferExecCompleted();
}

static void CompleteOnBankSpriteCallbackDummy2(void)
{
    if (gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
        OpponentBufferExecCompleted();
}

static void FreeTrainerSpriteAfterSlide(void)
{
    if (gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
    {
        FreeTrainerFrontPicPalette(gSprites[gBattlerSpriteIds[gActiveBattler]].oam.affineParam);
        FreeSpriteOamMatrix(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
        DestroySprite(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
        OpponentBufferExecCompleted();
    }
}

static void Intro_DelayAndEnd(void)
{
    if (--gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].introEndDelay == (u8)-1)
    {
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].introEndDelay = 0;
        OpponentBufferExecCompleted();
    }
}

static void Intro_WaitForShinyAnimAndHealthbox(void)
{
    bool8 healthboxAnimDone = FALSE;
    bool8 twoMons;
    bool8 hasPartner = FALSE;

    if (IsDoubleBattle()
     && !(gBattleTypeFlags & (BATTLE_TYPE_MULTI | BATTLE_TYPE_TWO_OPPONENTS))
     && !(gAbsentBattlerFlags & gBitTable[BATTLE_PARTNER(gActiveBattler)]))
        hasPartner = TRUE;

    if (!hasPartner)
    {
        if (gSprites[gHealthboxSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
            healthboxAnimDone = TRUE;
        twoMons = FALSE;
    }
    else
    {
        if (gSprites[gHealthboxSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy
         && gSprites[gHealthboxSpriteIds[BATTLE_PARTNER(gActiveBattler)]].callback == SpriteCallbackDummy)
            healthboxAnimDone = TRUE;
        twoMons = TRUE;
    }

    gBattleControllerOpponentHealthboxData = &gBattleSpritesDataPtr->healthBoxesData[gActiveBattler];
    gBattleControllerOpponentFlankHealthboxData = &gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)];

    if (healthboxAnimDone)
    {
        if (twoMons == TRUE)
        {
            if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim
             && gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].finishedShinyMonAnim)
            {
                gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim = FALSE;
                gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim = FALSE;
                gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].triedShinyMonAnim = FALSE;
                gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].finishedShinyMonAnim = FALSE;
                FreeSpriteTilesByTag(ANIM_TAG_GOLD_STARS);
                FreeSpritePaletteByTag(ANIM_TAG_GOLD_STARS);
            }
            else
            {
                return;
            }
        }
        else if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim)
        {
            if (GetBattlerPosition(gActiveBattler) == 3)
            {
                if (!gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].triedShinyMonAnim
                 && !gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].finishedShinyMonAnim)
                {
                    FreeSpriteTilesByTag(ANIM_TAG_GOLD_STARS);
                    FreeSpritePaletteByTag(ANIM_TAG_GOLD_STARS);
                }
                else
                {
                    return;
                }
            }
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim = FALSE;
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim = FALSE;
        }
        else
        {
            return;
        }

        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].introEndDelay = 3;
        gBattlerControllerFuncs[gActiveBattler] = Intro_DelayAndEnd;
    }
}

static void Intro_TryShinyAnimShowHealthbox(void)
{
    bool32 bgmRestored = FALSE;
    bool32 battlerAnimsDone = FALSE;
    bool8 hasPartner = FALSE;

    if (IsDoubleBattle()
     && !(gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_MULTI))
     && !(gAbsentBattlerFlags & gBitTable[BATTLE_PARTNER(gActiveBattler)]))
        hasPartner = TRUE;

    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim
     && !gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].ballAnimActive
     && !gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim)
        TryShinyAnimation(gActiveBattler, &gEnemyParty[gBattlerPartyIndexes[gActiveBattler]]);

    if (hasPartner
     && !gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].triedShinyMonAnim
     && !gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].ballAnimActive
     && !gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].finishedShinyMonAnim)
        TryShinyAnimation(BATTLE_PARTNER(gActiveBattler), &gEnemyParty[gBattlerPartyIndexes[BATTLE_PARTNER(gActiveBattler)]]);

    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].ballAnimActive
     && (!hasPartner || !gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].ballAnimActive))
    {
        if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].healthboxSlideInStarted)
        {
            if (hasPartner)
            {
                UpdateHealthboxAttribute(gHealthboxSpriteIds[BATTLE_PARTNER(gActiveBattler)], &gEnemyParty[gBattlerPartyIndexes[BATTLE_PARTNER(gActiveBattler)]], HEALTHBOX_ALL);
                StartHealthboxSlideIn(BATTLE_PARTNER(gActiveBattler));
                SetHealthboxSpriteVisible(gHealthboxSpriteIds[BATTLE_PARTNER(gActiveBattler)]);
            }
            UpdateHealthboxAttribute(gHealthboxSpriteIds[gActiveBattler], &gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], HEALTHBOX_ALL);
            StartHealthboxSlideIn(gActiveBattler);
            SetHealthboxSpriteVisible(gHealthboxSpriteIds[gActiveBattler]);
        }
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].healthboxSlideInStarted = TRUE;
    }

    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].waitForCry
        && gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].healthboxSlideInStarted
        && (!hasPartner || !gBattleSpritesDataPtr->healthBoxesData[BATTLE_PARTNER(gActiveBattler)].waitForCry)
        && !IsCryPlayingOrClearCrySongs())
    {
        if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].bgmRestored)
        {
            if (gBattleTypeFlags & BATTLE_TYPE_MULTI && gBattleTypeFlags & BATTLE_TYPE_LINK)
            {
                if (GetBattlerPosition(gActiveBattler) == 1)
                    m4aMPlayContinue(&gMPlayInfo_BGM);
            }
            else
            {
                m4aMPlayVolumeControl(&gMPlayInfo_BGM, TRACKS_ALL, 0x100);
            }
        }
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].bgmRestored = TRUE;
        bgmRestored = TRUE;
    }

    if (!hasPartner)
    {
        if (gSprites[gBattleControllerData[gActiveBattler]].callback == SpriteCallbackDummy
            && gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
        {
            battlerAnimsDone = TRUE;
        }
    }
    else
    {
        if (gSprites[gBattleControllerData[gActiveBattler]].callback == SpriteCallbackDummy
            && gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy
            && gSprites[gBattleControllerData[BATTLE_PARTNER(gActiveBattler)]].callback == SpriteCallbackDummy
            && gSprites[gBattlerSpriteIds[BATTLE_PARTNER(gActiveBattler)]].callback == SpriteCallbackDummy)
        {
            battlerAnimsDone = TRUE;
        }
    }

    if (bgmRestored && battlerAnimsDone)
    {
        if (hasPartner)
        {
            DestroySprite(&gSprites[gBattleControllerData[BATTLE_PARTNER(gActiveBattler)]]);
            SetBattlerShadowSpriteCallback(BATTLE_PARTNER(gActiveBattler), GetMonData(&gEnemyParty[gBattlerPartyIndexes[BATTLE_PARTNER(gActiveBattler)]], MON_DATA_SPECIES));
        }

        DestroySprite(&gSprites[gBattleControllerData[gActiveBattler]]);
        SetBattlerShadowSpriteCallback(gActiveBattler, GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_SPECIES));
        gBattleSpritesDataPtr->animationData->introAnimActive = FALSE;
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].bgmRestored = FALSE;
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].healthboxSlideInStarted = FALSE;

        gBattlerControllerFuncs[gActiveBattler] = Intro_WaitForShinyAnimAndHealthbox;
    }
}

static void TryShinyAnimAfterMonAnim(void)
{
    if (gSprites[gBattlerSpriteIds[gActiveBattler]].x2 == 0
        && !gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim
        && !gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim)
        TryShinyAnimation(gActiveBattler, &gEnemyParty[gBattlerPartyIndexes[gActiveBattler]]);

    if (gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy
     && gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim)
    {
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim = FALSE;
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim = FALSE;
        FreeSpriteTilesByTag(ANIM_TAG_GOLD_STARS);
        FreeSpritePaletteByTag(ANIM_TAG_GOLD_STARS);
        OpponentBufferExecCompleted();
    }
}

static void CompleteOnHealthbarDone(void)
{
    s16 hpValue = MoveBattleBar(gActiveBattler, gHealthboxSpriteIds[gActiveBattler], HEALTH_BAR, 0);
    SetHealthboxSpriteVisible(gHealthboxSpriteIds[gActiveBattler]);
    if (hpValue != -1)
        UpdateHpTextInHealthbox(gHealthboxSpriteIds[gActiveBattler], hpValue, HP_CURRENT);
    else
        OpponentBufferExecCompleted();
}

static void HideHealthboxAfterMonFaint(void)
{
    if (!gSprites[gBattlerSpriteIds[gActiveBattler]].inUse)
    {
        SetHealthboxSpriteInvisible(gHealthboxSpriteIds[gActiveBattler]);
        OpponentBufferExecCompleted();
    }
}

static void FreeMonSpriteAfterSwitchOutAnim(void)
{
    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].specialAnimActive)
    {
        FreeSpriteOamMatrix(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
        DestroySprite(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
        HideBattlerShadowSprite(gActiveBattler);
        SetHealthboxSpriteInvisible(gHealthboxSpriteIds[gActiveBattler]);
        OpponentBufferExecCompleted();
    }
}

static void CompleteOnInactiveTextPrinter(void)
{
    if (!IsTextPrinterActive(B_WIN_MSG))
        OpponentBufferExecCompleted();
}

static void DoHitAnimBlinkSpriteEffect(void)
{
    u8 spriteId = gBattlerSpriteIds[gActiveBattler];

    if (gSprites[spriteId].data[1] == 32)
    {
        gSprites[spriteId].data[1] = 0;
        gSprites[spriteId].invisible = FALSE;
        gDoingBattleAnim = FALSE;
        OpponentBufferExecCompleted();
    }
    else
    {
        if ((gSprites[spriteId].data[1] % 4) == 0)
            gSprites[spriteId].invisible ^= 1;
        gSprites[spriteId].data[1]++;
    }
}

static void SwitchIn_ShowSubstitute(void)
{
    if (gSprites[gHealthboxSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
    {
        if (gBattleSpritesDataPtr->battlerData[gActiveBattler].behindSubstitute)
            InitAndLaunchSpecialAnimation(gActiveBattler, gActiveBattler, gActiveBattler, B_ANIM_MON_TO_SUBSTITUTE);
        gBattlerControllerFuncs[gActiveBattler] = SwitchIn_HandleSoundAndEnd;
    }
}

static void SwitchIn_HandleSoundAndEnd(void)
{
    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].specialAnimActive && !IsCryPlayingOrClearCrySongs())
    {
        if (gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy
         || gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy_2)
        {
            m4aMPlayVolumeControl(&gMPlayInfo_BGM, TRACKS_ALL, 0x100);
            OpponentBufferExecCompleted();
        }
    }
}

static void SwitchIn_ShowHealthbox(void)
{
    if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim
     && gSprites[gBattlerSpriteIds[gActiveBattler]].callback == SpriteCallbackDummy)
    {
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim = FALSE;
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].finishedShinyMonAnim = FALSE;
        FreeSpriteTilesByTag(ANIM_TAG_GOLD_STARS);
        FreeSpritePaletteByTag(ANIM_TAG_GOLD_STARS);
        StartSpriteAnim(&gSprites[gBattlerSpriteIds[gActiveBattler]], 0);
        UpdateHealthboxAttribute(gHealthboxSpriteIds[gActiveBattler], &gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], HEALTHBOX_ALL);
        StartHealthboxSlideIn(gActiveBattler);
        SetHealthboxSpriteVisible(gHealthboxSpriteIds[gActiveBattler]);
        CopyBattleSpriteInvisibility(gActiveBattler);
        gBattlerControllerFuncs[gActiveBattler] = SwitchIn_ShowSubstitute;
    }
}

static void SwitchIn_TryShinyAnim(void)
{
    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].triedShinyMonAnim
     && !gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].ballAnimActive)
        TryShinyAnimation(gActiveBattler, &gEnemyParty[gBattlerPartyIndexes[gActiveBattler]]);

    if (gSprites[gBattleControllerData[gActiveBattler]].callback == SpriteCallbackDummy
     && !gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].ballAnimActive)
    {
        DestroySprite(&gSprites[gBattleControllerData[gActiveBattler]]);
        SetBattlerShadowSpriteCallback(gActiveBattler, GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_SPECIES));
        gBattlerControllerFuncs[gActiveBattler] = SwitchIn_ShowHealthbox;
    }
}

static void CompleteOnFinishedStatusAnimation(void)
{
    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].statusAnimActive)
        OpponentBufferExecCompleted();
}

static void CompleteOnFinishedBattleAnimation(void)
{
    if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animFromTableActive)
        OpponentBufferExecCompleted();
}

static void OpponentBufferExecCompleted(void)
{
    gBattlerControllerFuncs[gActiveBattler] = OpponentBufferRunCommand;
    if (gBattleTypeFlags & BATTLE_TYPE_LINK)
    {
        u8 playerId = GetMultiplayerId();

        PrepareBufferDataTransferLink(B_COMM_CONTROLLER_IS_DONE, 4, &playerId);
        gBattleBufferA[gActiveBattler][0] = CONTROLLER_TERMINATOR_NOP;
    }
    else
    {
        gBattleControllerExecFlags &= ~gBitTable[gActiveBattler];
    }
}

static void OpponentHandleGetMonData(void)
{
    u8 monData[sizeof(struct Pokemon) * 2 + 56]; // this allows to get full data of two Pokémon, trying to get more will result in overwriting data
    u32 size = 0;
    u8 monToCheck;
    s32 i;

    if (gBattleBufferA[gActiveBattler][2] == 0)
    {
        size += GetOpponentMonData(gBattlerPartyIndexes[gActiveBattler], monData);
    }
    else
    {
        monToCheck = gBattleBufferA[gActiveBattler][2];
        for (i = 0; i < PARTY_SIZE; i++)
        {
            if (monToCheck & 1)
                size += GetOpponentMonData(i, monData + size);
            monToCheck >>= 1;
        }
    }
    BtlController_EmitDataTransfer(B_COMM_TO_ENGINE, size, monData);
    OpponentBufferExecCompleted();
}

static u32 GetOpponentMonData(u8 monId, u8 *dst)
{
    struct BattlePokemon battleMon;
    struct MovePpInfo moveData;
    u8 nickname[POKEMON_NAME_BUFFER_SIZE];
    u8 *src;
    s16 data16;
    u32 data32;
    s32 size = 0;

    switch (gBattleBufferA[gActiveBattler][1])
    {
    case REQUEST_ALL_BATTLE:
        battleMon.species = GetMonData(&gEnemyParty[monId], MON_DATA_SPECIES);
        battleMon.item = GetMonData(&gEnemyParty[monId], MON_DATA_HELD_ITEM);
        for (size = 0; size < MAX_MON_MOVES; size++)
        {
            battleMon.moves[size] = GetMonData(&gEnemyParty[monId], MON_DATA_MOVE1 + size);
            battleMon.pp[size] = GetMonData(&gEnemyParty[monId], MON_DATA_PP1 + size);
        }
        battleMon.ppBonuses = GetMonData(&gEnemyParty[monId], MON_DATA_PP_BONUSES);
        battleMon.friendship = GetMonData(&gEnemyParty[monId], MON_DATA_FRIENDSHIP);
        battleMon.experience = GetMonData(&gEnemyParty[monId], MON_DATA_EXP);
        battleMon.hpIV = GetMonData(&gEnemyParty[monId], MON_DATA_HP_IV);
        battleMon.attackIV = GetMonData(&gEnemyParty[monId], MON_DATA_ATK_IV);
        battleMon.defenseIV = GetMonData(&gEnemyParty[monId], MON_DATA_DEF_IV);
        battleMon.speedIV = GetMonData(&gEnemyParty[monId], MON_DATA_SPEED_IV);
        battleMon.spAttackIV = GetMonData(&gEnemyParty[monId], MON_DATA_SPATK_IV);
        battleMon.spDefenseIV = GetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_IV);
        battleMon.personality = GetMonData(&gEnemyParty[monId], MON_DATA_PERSONALITY);
        battleMon.status1 = GetMonData(&gEnemyParty[monId], MON_DATA_STATUS);
        battleMon.level = GetMonData(&gEnemyParty[monId], MON_DATA_LEVEL);
        battleMon.hp = GetMonData(&gEnemyParty[monId], MON_DATA_HP);
        battleMon.maxHP = GetMonData(&gEnemyParty[monId], MON_DATA_MAX_HP);
        battleMon.attack = GetMonData(&gEnemyParty[monId], MON_DATA_ATK);
        battleMon.defense = GetMonData(&gEnemyParty[monId], MON_DATA_DEF);
        battleMon.speed = GetMonData(&gEnemyParty[monId], MON_DATA_SPEED);
        battleMon.spAttack = GetMonData(&gEnemyParty[monId], MON_DATA_SPATK);
        battleMon.spDefense = GetMonData(&gEnemyParty[monId], MON_DATA_SPDEF);
        battleMon.isEgg = GetMonData(&gEnemyParty[monId], MON_DATA_IS_EGG);
        battleMon.abilityNum = GetMonData(&gEnemyParty[monId], MON_DATA_ABILITY_NUM);
        battleMon.otId = GetMonData(&gEnemyParty[monId], MON_DATA_OT_ID);
        GetMonData(&gEnemyParty[monId], MON_DATA_NICKNAME, nickname);
        StringCopy_Nickname(battleMon.nickname, nickname);
        GetMonData(&gEnemyParty[monId], MON_DATA_OT_NAME, battleMon.otName);
        src = (u8 *)&battleMon;
        for (size = 0; size < sizeof(battleMon); size++)
            dst[size] = src[size];
        break;
    case REQUEST_SPECIES_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_SPECIES);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_HELDITEM_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_HELD_ITEM);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_MOVES_PP_BATTLE:
        for (size = 0; size < MAX_MON_MOVES; size++)
        {
            moveData.moves[size] = GetMonData(&gEnemyParty[monId], MON_DATA_MOVE1 + size);
            moveData.pp[size] = GetMonData(&gEnemyParty[monId], MON_DATA_PP1 + size);
        }
        moveData.ppBonuses = GetMonData(&gEnemyParty[monId], MON_DATA_PP_BONUSES);
        src = (u8 *)(&moveData);
        for (size = 0; size < sizeof(moveData); size++)
            dst[size] = src[size];
        break;
    case REQUEST_MOVE1_BATTLE:
    case REQUEST_MOVE2_BATTLE:
    case REQUEST_MOVE3_BATTLE:
    case REQUEST_MOVE4_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_MOVE1 + gBattleBufferA[gActiveBattler][1] - REQUEST_MOVE1_BATTLE);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_PP_DATA_BATTLE:
        for (size = 0; size < MAX_MON_MOVES; size++)
            dst[size] = GetMonData(&gEnemyParty[monId], MON_DATA_PP1 + size);
        dst[size] = GetMonData(&gEnemyParty[monId], MON_DATA_PP_BONUSES);
        size++;
        break;
    case REQUEST_PPMOVE1_BATTLE:
    case REQUEST_PPMOVE2_BATTLE:
    case REQUEST_PPMOVE3_BATTLE:
    case REQUEST_PPMOVE4_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_PP1 + gBattleBufferA[gActiveBattler][1] - REQUEST_PPMOVE1_BATTLE);
        size = 1;
        break;
    case REQUEST_OTID_BATTLE:
        data32 = GetMonData(&gEnemyParty[monId], MON_DATA_OT_ID);
        dst[0] = (data32 & 0x000000FF);
        dst[1] = (data32 & 0x0000FF00) >> 8;
        dst[2] = (data32 & 0x00FF0000) >> 16;
        size = 3;
        break;
    case REQUEST_EXP_BATTLE:
        data32 = GetMonData(&gEnemyParty[monId], MON_DATA_EXP);
        dst[0] = (data32 & 0x000000FF);
        dst[1] = (data32 & 0x0000FF00) >> 8;
        dst[2] = (data32 & 0x00FF0000) >> 16;
        size = 3;
        break;
    case REQUEST_HP_EV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_HP_EV);
        size = 1;
        break;
    case REQUEST_ATK_EV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_ATK_EV);
        size = 1;
        break;
    case REQUEST_DEF_EV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_DEF_EV);
        size = 1;
        break;
    case REQUEST_SPEED_EV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SPEED_EV);
        size = 1;
        break;
    case REQUEST_SPATK_EV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SPATK_EV);
        size = 1;
        break;
    case REQUEST_SPDEF_EV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_EV);
        size = 1;
        break;
    case REQUEST_FRIENDSHIP_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_FRIENDSHIP);
        size = 1;
        break;
    case REQUEST_POKERUS_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_POKERUS);
        size = 1;
        break;
    case REQUEST_MET_LOCATION_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_MET_LOCATION);
        size = 1;
        break;
    case REQUEST_MET_LEVEL_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_MET_LEVEL);
        size = 1;
        break;
    case REQUEST_MET_GAME_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_MET_GAME);
        size = 1;
        break;
    case REQUEST_POKEBALL_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_POKEBALL);
        size = 1;
        break;
    case REQUEST_ALL_IVS_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_HP_IV);
        dst[1] = GetMonData(&gEnemyParty[monId], MON_DATA_ATK_IV);
        dst[2] = GetMonData(&gEnemyParty[monId], MON_DATA_DEF_IV);
        dst[3] = GetMonData(&gEnemyParty[monId], MON_DATA_SPEED_IV);
        dst[4] = GetMonData(&gEnemyParty[monId], MON_DATA_SPATK_IV);
        dst[5] = GetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_IV);
        size = 6;
        break;
    case REQUEST_HP_IV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_HP_IV);
        size = 1;
        break;
    case REQUEST_ATK_IV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_ATK_IV);
        size = 1;
        break;
    case REQUEST_DEF_IV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_DEF_IV);
        size = 1;
        break;
    case REQUEST_SPEED_IV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SPEED_IV);
        size = 1;
        break;
    case REQUEST_SPATK_IV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SPATK_IV);
        size = 1;
        break;
    case REQUEST_SPDEF_IV_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_IV);
        size = 1;
        break;
    case REQUEST_PERSONALITY_BATTLE:
        data32 = GetMonData(&gEnemyParty[monId], MON_DATA_PERSONALITY);
        dst[0] = (data32 & 0x000000FF);
        dst[1] = (data32 & 0x0000FF00) >> 8;
        dst[2] = (data32 & 0x00FF0000) >> 16;
        dst[3] = (data32 & 0xFF000000) >> 24;
        size = 4;
        break;
    case REQUEST_CHECKSUM_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_CHECKSUM);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_STATUS_BATTLE:
        data32 = GetMonData(&gEnemyParty[monId], MON_DATA_STATUS);
        dst[0] = (data32 & 0x000000FF);
        dst[1] = (data32 & 0x0000FF00) >> 8;
        dst[2] = (data32 & 0x00FF0000) >> 16;
        dst[3] = (data32 & 0xFF000000) >> 24;
        size = 4;
        break;
    case REQUEST_LEVEL_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_LEVEL);
        size = 1;
        break;
    case REQUEST_HP_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_HP);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_MAX_HP_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_MAX_HP);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_ATK_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_ATK);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_DEF_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_DEF);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_SPEED_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_SPEED);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_SPATK_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_SPATK);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_SPDEF_BATTLE:
        data16 = GetMonData(&gEnemyParty[monId], MON_DATA_SPDEF);
        dst[0] = data16;
        dst[1] = data16 >> 8;
        size = 2;
        break;
    case REQUEST_COOL_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_COOL);
        size = 1;
        break;
    case REQUEST_BEAUTY_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_BEAUTY);
        size = 1;
        break;
    case REQUEST_CUTE_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_CUTE);
        size = 1;
        break;
    case REQUEST_SMART_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SMART);
        size = 1;
        break;
    case REQUEST_TOUGH_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_TOUGH);
        size = 1;
        break;
    case REQUEST_SHEEN_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SHEEN);
        size = 1;
        break;
    case REQUEST_COOL_RIBBON_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_COOL_RIBBON);
        size = 1;
        break;
    case REQUEST_BEAUTY_RIBBON_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_BEAUTY_RIBBON);
        size = 1;
        break;
    case REQUEST_CUTE_RIBBON_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_CUTE_RIBBON);
        size = 1;
        break;
    case REQUEST_SMART_RIBBON_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_SMART_RIBBON);
        size = 1;
        break;
    case REQUEST_TOUGH_RIBBON_BATTLE:
        dst[0] = GetMonData(&gEnemyParty[monId], MON_DATA_TOUGH_RIBBON);
        size = 1;
        break;
    }

    return size;
}

static void OpponentHandleGetRawMonData(void)
{
    struct BattlePokemon battleMon;
    u8 *src = (u8 *)&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]] + gBattleBufferA[gActiveBattler][1];
    u8 *dst = (u8 *)&battleMon + gBattleBufferA[gActiveBattler][1];
    u8 i;

    for (i = 0; i < gBattleBufferA[gActiveBattler][2]; i++)
        dst[i] = src[i];

    BtlController_EmitDataTransfer(B_COMM_TO_ENGINE, gBattleBufferA[gActiveBattler][2], dst);
    OpponentBufferExecCompleted();
}

static void OpponentHandleSetMonData(void)
{
    u8 monToCheck;
    u8 i;

    if (gBattleBufferA[gActiveBattler][2] == 0)
    {
        SetOpponentMonData(gBattlerPartyIndexes[gActiveBattler]);
    }
    else
    {
        monToCheck = gBattleBufferA[gActiveBattler][2];
        for (i = 0; i < PARTY_SIZE; i++)
        {
            if (monToCheck & 1)
                SetOpponentMonData(i);
            monToCheck >>= 1;
        }
    }
    OpponentBufferExecCompleted();
}

static void SetOpponentMonData(u8 monId)
{
    struct BattlePokemon *battlePokemon = (struct BattlePokemon *)&gBattleBufferA[gActiveBattler][3];
    struct MovePpInfo *moveData = (struct MovePpInfo *)&gBattleBufferA[gActiveBattler][3];
    s32 i;

    switch (gBattleBufferA[gActiveBattler][1])
    {
    case REQUEST_ALL_BATTLE:
        {
            u8 iv;

            SetMonData(&gEnemyParty[monId], MON_DATA_SPECIES, &battlePokemon->species);
            SetMonData(&gEnemyParty[monId], MON_DATA_HELD_ITEM, &battlePokemon->item);
            for (i = 0; i < MAX_MON_MOVES; i++)
            {
                SetMonData(&gEnemyParty[monId], MON_DATA_MOVE1 + i, &battlePokemon->moves[i]);
                SetMonData(&gEnemyParty[monId], MON_DATA_PP1 + i, &battlePokemon->pp[i]);
            }
            SetMonData(&gEnemyParty[monId], MON_DATA_PP_BONUSES, &battlePokemon->ppBonuses);
            SetMonData(&gEnemyParty[monId], MON_DATA_FRIENDSHIP, &battlePokemon->friendship);
            SetMonData(&gEnemyParty[monId], MON_DATA_EXP, &battlePokemon->experience);
            iv = battlePokemon->hpIV;
            SetMonData(&gEnemyParty[monId], MON_DATA_HP_IV, &iv);
            iv = battlePokemon->attackIV;
            SetMonData(&gEnemyParty[monId], MON_DATA_ATK_IV, &iv);
            iv = battlePokemon->defenseIV;
            SetMonData(&gEnemyParty[monId], MON_DATA_DEF_IV, &iv);
            iv = battlePokemon->speedIV;
            SetMonData(&gEnemyParty[monId], MON_DATA_SPEED_IV, &iv);
            iv = battlePokemon->spAttackIV;
            SetMonData(&gEnemyParty[monId], MON_DATA_SPATK_IV, &iv);
            iv = battlePokemon->spDefenseIV;
            SetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_IV, &iv);
            SetMonData(&gEnemyParty[monId], MON_DATA_PERSONALITY, &battlePokemon->personality);
            SetMonData(&gEnemyParty[monId], MON_DATA_STATUS, &battlePokemon->status1);
            SetMonData(&gEnemyParty[monId], MON_DATA_LEVEL, &battlePokemon->level);
            SetMonData(&gEnemyParty[monId], MON_DATA_HP, &battlePokemon->hp);
            SetMonData(&gEnemyParty[monId], MON_DATA_MAX_HP, &battlePokemon->maxHP);
            SetMonData(&gEnemyParty[monId], MON_DATA_ATK, &battlePokemon->attack);
            SetMonData(&gEnemyParty[monId], MON_DATA_DEF, &battlePokemon->defense);
            SetMonData(&gEnemyParty[monId], MON_DATA_SPEED, &battlePokemon->speed);
            SetMonData(&gEnemyParty[monId], MON_DATA_SPATK, &battlePokemon->spAttack);
            SetMonData(&gEnemyParty[monId], MON_DATA_SPDEF, &battlePokemon->spDefense);
        }
        break;
    case REQUEST_SPECIES_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPECIES, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_HELDITEM_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_HELD_ITEM, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_MOVES_PP_BATTLE:
        for (i = 0; i < MAX_MON_MOVES; i++)
        {
            SetMonData(&gEnemyParty[monId], MON_DATA_MOVE1 + i, &moveData->moves[i]);
            SetMonData(&gEnemyParty[monId], MON_DATA_PP1 + i, &moveData->pp[i]);
        }
        SetMonData(&gEnemyParty[monId], MON_DATA_PP_BONUSES, &moveData->ppBonuses);
        break;
    case REQUEST_MOVE1_BATTLE:
    case REQUEST_MOVE2_BATTLE:
    case REQUEST_MOVE3_BATTLE:
    case REQUEST_MOVE4_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_MOVE1 + gBattleBufferA[gActiveBattler][1] - REQUEST_MOVE1_BATTLE, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_PP_DATA_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_PP1, &gBattleBufferA[gActiveBattler][3]);
        SetMonData(&gEnemyParty[monId], MON_DATA_PP2, &gBattleBufferA[gActiveBattler][4]);
        SetMonData(&gEnemyParty[monId], MON_DATA_PP3, &gBattleBufferA[gActiveBattler][5]);
        SetMonData(&gEnemyParty[monId], MON_DATA_PP4, &gBattleBufferA[gActiveBattler][6]);
        SetMonData(&gEnemyParty[monId], MON_DATA_PP_BONUSES, &gBattleBufferA[gActiveBattler][7]);
        break;
    case REQUEST_PPMOVE1_BATTLE:
    case REQUEST_PPMOVE2_BATTLE:
    case REQUEST_PPMOVE3_BATTLE:
    case REQUEST_PPMOVE4_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_PP1 + gBattleBufferA[gActiveBattler][1] - REQUEST_PPMOVE1_BATTLE, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_OTID_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_OT_ID, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_EXP_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_EXP, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_HP_EV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_HP_EV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_ATK_EV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_ATK_EV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_DEF_EV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_DEF_EV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPEED_EV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPEED_EV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPATK_EV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPATK_EV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPDEF_EV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_EV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_FRIENDSHIP_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_FRIENDSHIP, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_POKERUS_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_POKERUS, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_MET_LOCATION_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_MET_LOCATION, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_MET_LEVEL_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_MET_LEVEL, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_MET_GAME_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_MET_GAME, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_POKEBALL_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_POKEBALL, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_ALL_IVS_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_HP_IV, &gBattleBufferA[gActiveBattler][3]);
        SetMonData(&gEnemyParty[monId], MON_DATA_ATK_IV, &gBattleBufferA[gActiveBattler][4]);
        SetMonData(&gEnemyParty[monId], MON_DATA_DEF_IV, &gBattleBufferA[gActiveBattler][5]);
        SetMonData(&gEnemyParty[monId], MON_DATA_SPEED_IV, &gBattleBufferA[gActiveBattler][6]);
        SetMonData(&gEnemyParty[monId], MON_DATA_SPATK_IV, &gBattleBufferA[gActiveBattler][7]);
        SetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_IV, &gBattleBufferA[gActiveBattler][8]);
        break;
    case REQUEST_HP_IV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_HP_IV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_ATK_IV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_ATK_IV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_DEF_IV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_DEF_IV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPEED_IV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPEED_IV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPATK_IV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPATK_IV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPDEF_IV_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPDEF_IV, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_PERSONALITY_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_PERSONALITY, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_CHECKSUM_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_CHECKSUM, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_STATUS_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_STATUS, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_LEVEL_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_LEVEL, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_HP_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_HP, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_MAX_HP_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_MAX_HP, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_ATK_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_ATK, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_DEF_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_DEF, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPEED_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPEED, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPATK_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPATK, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SPDEF_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SPDEF, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_COOL_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_COOL, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_BEAUTY_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_BEAUTY, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_CUTE_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_CUTE, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SMART_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SMART, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_TOUGH_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_TOUGH, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SHEEN_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SHEEN, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_COOL_RIBBON_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_COOL_RIBBON, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_BEAUTY_RIBBON_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_BEAUTY_RIBBON, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_CUTE_RIBBON_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_CUTE_RIBBON, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_SMART_RIBBON_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_SMART_RIBBON, &gBattleBufferA[gActiveBattler][3]);
        break;
    case REQUEST_TOUGH_RIBBON_BATTLE:
        SetMonData(&gEnemyParty[monId], MON_DATA_TOUGH_RIBBON, &gBattleBufferA[gActiveBattler][3]);
        break;
    }
}

static void OpponentHandleSetRawMonData(void)
{
    u8 *dst = (u8 *)&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]] + gBattleBufferA[gActiveBattler][1];
    u8 i;

    for (i = 0; i < gBattleBufferA[gActiveBattler][2]; i++)
        dst[i] = gBattleBufferA[gActiveBattler][3 + i];

    OpponentBufferExecCompleted();
}

static void OpponentHandleLoadMonSprite(void)
{
    u16 species = GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_SPECIES);

    BattleLoadOpponentMonSpriteGfx(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], gActiveBattler);
    SetMultiuseSpriteTemplateToPokemon(species, GetBattlerPosition(gActiveBattler));

    gBattlerSpriteIds[gActiveBattler] = CreateSprite(&gMultiuseSpriteTemplate,
                                               GetBattlerSpriteCoord(gActiveBattler, BATTLER_COORD_X_2),
                                               GetBattlerSpriteDefault_Y(gActiveBattler),
                                               GetBattlerSpriteSubpriority(gActiveBattler));

    gSprites[gBattlerSpriteIds[gActiveBattler]].x2 = -DISPLAY_WIDTH;
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[0] = gActiveBattler;
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[2] = species;
    gSprites[gBattlerSpriteIds[gActiveBattler]].oam.paletteNum = gActiveBattler;
    StartSpriteAnim(&gSprites[gBattlerSpriteIds[gActiveBattler]], gBattleMonForms[gActiveBattler]);

    SetBattlerShadowSpriteCallback(gActiveBattler, GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_SPECIES));

    gBattlerControllerFuncs[gActiveBattler] = TryShinyAnimAfterMonAnim;
}

static void OpponentHandleSwitchInAnim(void)
{
    *(gBattleStruct->monToSwitchIntoId + gActiveBattler) = PARTY_SIZE;
    gBattlerPartyIndexes[gActiveBattler] = gBattleBufferA[gActiveBattler][1];
    StartSendOutAnim(gActiveBattler, gBattleBufferA[gActiveBattler][2]);
    gBattlerControllerFuncs[gActiveBattler] = SwitchIn_TryShinyAnim;
}

static void StartSendOutAnim(u8 battler, bool8 dontClearSubstituteBit)
{
    u16 species;

    ClearTemporarySpeciesSpriteData(battler, dontClearSubstituteBit);
    gBattlerPartyIndexes[battler] = gBattleBufferA[battler][1];
    species = GetMonData(&gEnemyParty[gBattlerPartyIndexes[battler]], MON_DATA_SPECIES);
    gBattleControllerData[battler] = CreateInvisibleSpriteWithCallback(SpriteCB_WaitForBattlerBallReleaseAnim);
    BattleLoadOpponentMonSpriteGfx(&gEnemyParty[gBattlerPartyIndexes[battler]], battler);
    SetMultiuseSpriteTemplateToPokemon(species, GetBattlerPosition(battler));

    gBattlerSpriteIds[battler] = CreateSprite(&gMultiuseSpriteTemplate,
                                        GetBattlerSpriteCoord(battler, BATTLER_COORD_X_2),
                                        GetBattlerSpriteDefault_Y(battler),
                                        GetBattlerSpriteSubpriority(battler));

    gSprites[gBattlerSpriteIds[battler]].data[0] = battler;
    gSprites[gBattlerSpriteIds[battler]].data[2] = species;

    gSprites[gBattleControllerData[battler]].data[1] = gBattlerSpriteIds[battler];
    gSprites[gBattleControllerData[battler]].data[2] = battler;

    gSprites[gBattlerSpriteIds[battler]].oam.paletteNum = battler;

    StartSpriteAnim(&gSprites[gBattlerSpriteIds[battler]], gBattleMonForms[battler]);

    gSprites[gBattlerSpriteIds[battler]].invisible = TRUE;
    gSprites[gBattlerSpriteIds[battler]].callback = SpriteCallbackDummy;

    gSprites[gBattleControllerData[battler]].data[0] = DoPokeballSendOutAnimation(0, POKEBALL_OPPONENT_SENDOUT);
}

static void OpponentHandleReturnMonToBall(void)
{
    if (gBattleBufferA[gActiveBattler][1] == 0)
    {
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 0;
        gBattlerControllerFuncs[gActiveBattler] = DoSwitchOutAnimation;
    }
    else
    {
        FreeSpriteOamMatrix(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
        DestroySprite(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
        HideBattlerShadowSprite(gActiveBattler);
        SetHealthboxSpriteInvisible(gHealthboxSpriteIds[gActiveBattler]);
        OpponentBufferExecCompleted();
    }
}

static void DoSwitchOutAnimation(void)
{
    switch (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState)
    {
    case 0:
        if (gBattleSpritesDataPtr->battlerData[gActiveBattler].behindSubstitute)
            InitAndLaunchSpecialAnimation(gActiveBattler, gActiveBattler, gActiveBattler, B_ANIM_SUBSTITUTE_TO_MON);

        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 1;
        break;
    case 1:
        if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].specialAnimActive)
        {
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 0;
            InitAndLaunchSpecialAnimation(gActiveBattler, gActiveBattler, gActiveBattler, B_ANIM_SWITCH_OUT_OPPONENT_MON);
            gBattlerControllerFuncs[gActiveBattler] = FreeMonSpriteAfterSwitchOutAnim;
        }
        break;
    }
}

#define sSpeedX data[0]

static void OpponentHandleDrawTrainerPic(void)
{
    u32 trainerPicId;
    s16 xPos;

    if (gBattleTypeFlags & BATTLE_TYPE_SECRET_BASE)
    {
        trainerPicId = GetSecretBaseTrainerPicIndex();
    }
    else if (gTrainerBattleOpponent_A == TRAINER_FRONTIER_BRAIN)
    {
        trainerPicId = GetFrontierBrainTrainerPicIndex();
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_TRAINER_HILL)
    {
        if (gBattleTypeFlags & BATTLE_TYPE_TWO_OPPONENTS)
        {
            if (gActiveBattler == 1)
                trainerPicId = GetTrainerHillTrainerFrontSpriteId(gTrainerBattleOpponent_A);
            else
                trainerPicId = GetTrainerHillTrainerFrontSpriteId(gTrainerBattleOpponent_B);
        }
        else
        {
            trainerPicId = GetTrainerHillTrainerFrontSpriteId(gTrainerBattleOpponent_A);
        }
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_FRONTIER)
    {
        if (gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_TOWER_LINK_MULTI))
        {
            if (gActiveBattler == 1)
                trainerPicId = GetFrontierTrainerFrontSpriteId(gTrainerBattleOpponent_A);
            else
                trainerPicId = GetFrontierTrainerFrontSpriteId(gTrainerBattleOpponent_B);
        }
        else
        {
            trainerPicId = GetFrontierTrainerFrontSpriteId(gTrainerBattleOpponent_A);
        }
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_EREADER_TRAINER)
    {
        trainerPicId = GetEreaderTrainerFrontSpriteId();
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_TWO_OPPONENTS)
    {
        if (gActiveBattler != 1)
            trainerPicId = gTrainers[gTrainerBattleOpponent_B].trainerPic;
        else
            trainerPicId = gTrainers[gTrainerBattleOpponent_A].trainerPic;
    }
    else
    {
        trainerPicId = gTrainers[gTrainerBattleOpponent_A].trainerPic;
    }

    if (gBattleTypeFlags & (BATTLE_TYPE_MULTI | BATTLE_TYPE_TWO_OPPONENTS))
    {
        if ((GetBattlerPosition(gActiveBattler) & BIT_FLANK) != 0) // second mon
            xPos = 152;
        else // first mon
            xPos = 200;
    }
    else
    {
        xPos = 176;
    }

    DecompressTrainerFrontPic(trainerPicId, gActiveBattler);
    SetMultiuseSpriteTemplateToTrainerBack(trainerPicId, GetBattlerPosition(gActiveBattler));
    gBattlerSpriteIds[gActiveBattler] = CreateSprite(&gMultiuseSpriteTemplate,
                                               xPos,
                                               (8 - gTrainerFrontPicCoords[trainerPicId].size) * 4 + 40,
                                               GetBattlerSpriteSubpriority(gActiveBattler));

    gSprites[gBattlerSpriteIds[gActiveBattler]].x2 = -DISPLAY_WIDTH;
    gSprites[gBattlerSpriteIds[gActiveBattler]].sSpeedX = 2;
    gSprites[gBattlerSpriteIds[gActiveBattler]].oam.paletteNum = IndexOfSpritePaletteTag(gTrainerFrontPicPaletteTable[trainerPicId].tag);
    gSprites[gBattlerSpriteIds[gActiveBattler]].oam.affineParam = trainerPicId;
    gSprites[gBattlerSpriteIds[gActiveBattler]].callback = SpriteCB_TrainerSlideIn;

    gBattlerControllerFuncs[gActiveBattler] = CompleteOnBattlerSpriteCallbackDummy;
}

static void OpponentHandleTrainerSlide(void)
{
    u32 trainerPicId;

    if (gBattleTypeFlags & BATTLE_TYPE_SECRET_BASE)
    {
        trainerPicId = GetSecretBaseTrainerPicIndex();
    }
    else if (gTrainerBattleOpponent_A == TRAINER_FRONTIER_BRAIN)
    {
        trainerPicId = GetFrontierBrainTrainerPicIndex();
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_TRAINER_HILL)
    {
        if (gBattleTypeFlags & BATTLE_TYPE_TWO_OPPONENTS)
        {
            if (gActiveBattler == 1)
                trainerPicId = GetTrainerHillTrainerFrontSpriteId(gTrainerBattleOpponent_A);
            else
                trainerPicId = GetTrainerHillTrainerFrontSpriteId(gTrainerBattleOpponent_B);
        }
        else
        {
            trainerPicId = GetTrainerHillTrainerFrontSpriteId(gTrainerBattleOpponent_A);
        }
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_FRONTIER)
    {
        if (gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_TOWER_LINK_MULTI))
        {
            if (gActiveBattler == 1)
                trainerPicId = GetFrontierTrainerFrontSpriteId(gTrainerBattleOpponent_A);
            else
                trainerPicId = GetFrontierTrainerFrontSpriteId(gTrainerBattleOpponent_B);
        }
        else
        {
            trainerPicId = GetFrontierTrainerFrontSpriteId(gTrainerBattleOpponent_A);
        }
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_EREADER_TRAINER)
    {
        trainerPicId = GetEreaderTrainerFrontSpriteId();
    }
    else if (gBattleTypeFlags & BATTLE_TYPE_TWO_OPPONENTS)
    {
        if (gActiveBattler != 1)
            trainerPicId = gTrainers[gTrainerBattleOpponent_B].trainerPic;
        else
            trainerPicId = gTrainers[gTrainerBattleOpponent_A].trainerPic;
    }
    else
    {
        trainerPicId = gTrainers[gTrainerBattleOpponent_A].trainerPic;
    }

    DecompressTrainerFrontPic(trainerPicId, gActiveBattler);
    SetMultiuseSpriteTemplateToTrainerBack(trainerPicId, GetBattlerPosition(gActiveBattler));
    gBattlerSpriteIds[gActiveBattler] = CreateSprite(&gMultiuseSpriteTemplate, 176, (8 - gTrainerFrontPicCoords[trainerPicId].size) * 4 + 40, 0x1E);

    gSprites[gBattlerSpriteIds[gActiveBattler]].x2 = 96;
    gSprites[gBattlerSpriteIds[gActiveBattler]].x += 32;
    gSprites[gBattlerSpriteIds[gActiveBattler]].sSpeedX = -2;
    gSprites[gBattlerSpriteIds[gActiveBattler]].oam.paletteNum = IndexOfSpritePaletteTag(gTrainerFrontPicPaletteTable[trainerPicId].tag);
    gSprites[gBattlerSpriteIds[gActiveBattler]].oam.affineParam = trainerPicId;
    gSprites[gBattlerSpriteIds[gActiveBattler]].callback = SpriteCB_TrainerSlideIn;

    gBattlerControllerFuncs[gActiveBattler] = CompleteOnBankSpriteCallbackDummy2;
}

#undef sSpeedX

static void OpponentHandleTrainerSlideBack(void)
{
    SetSpritePrimaryCoordsFromSecondaryCoords(&gSprites[gBattlerSpriteIds[gActiveBattler]]);
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[0] = 35;
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[2] = 280;
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[4] = gSprites[gBattlerSpriteIds[gActiveBattler]].y;
    gSprites[gBattlerSpriteIds[gActiveBattler]].callback = StartAnimLinearTranslation;
    StoreSpriteCallbackInData6(&gSprites[gBattlerSpriteIds[gActiveBattler]], SpriteCallbackDummy);
    gBattlerControllerFuncs[gActiveBattler] = FreeTrainerSpriteAfterSlide;
}

static void OpponentHandleFaintAnimation(void)
{
    if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState == 0)
    {
        if (gBattleSpritesDataPtr->battlerData[gActiveBattler].behindSubstitute)
            InitAndLaunchSpecialAnimation(gActiveBattler, gActiveBattler, gActiveBattler, B_ANIM_SUBSTITUTE_TO_MON);
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState++;
    }
    else
    {
        if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].specialAnimActive)
        {
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 0;
            PlaySE12WithPanning(SE_FAINT, SOUND_PAN_TARGET);
            gSprites[gBattlerSpriteIds[gActiveBattler]].callback = SpriteCB_FaintOpponentMon;
            gBattlerControllerFuncs[gActiveBattler] = HideHealthboxAfterMonFaint;
        }
    }
}

static void OpponentHandlePaletteFade(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleSuccessBallThrowAnim(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleBallThrow(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandlePause(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleMoveAnimation(void)
{
    if (!IsBattleSEPlaying(gActiveBattler))
    {
        u16 move = gBattleBufferA[gActiveBattler][1] | (gBattleBufferA[gActiveBattler][2] << 8);

        gAnimMoveTurn = gBattleBufferA[gActiveBattler][3];
        gAnimMovePower = gBattleBufferA[gActiveBattler][4] | (gBattleBufferA[gActiveBattler][5] << 8);
        gAnimMoveDmg = gBattleBufferA[gActiveBattler][6] | (gBattleBufferA[gActiveBattler][7] << 8) | (gBattleBufferA[gActiveBattler][8] << 16) | (gBattleBufferA[gActiveBattler][9] << 24);
        gAnimFriendship = gBattleBufferA[gActiveBattler][10];
        gWeatherMoveAnim = gBattleBufferA[gActiveBattler][12] | (gBattleBufferA[gActiveBattler][13] << 8);
        gAnimDisableStructPtr = (struct DisableStruct *)&gBattleBufferA[gActiveBattler][16];
        gTransformedPersonalities[gActiveBattler] = gAnimDisableStructPtr->transformedMonPersonality;
        if (IsMoveWithoutAnimation(move, gAnimMoveTurn)) // always returns FALSE
        {
            OpponentBufferExecCompleted();
        }
        else
        {
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 0;
            gBattlerControllerFuncs[gActiveBattler] = OpponentDoMoveAnimation;
        }
    }
}

static void OpponentDoMoveAnimation(void)
{
    u16 move = gBattleBufferA[gActiveBattler][1] | (gBattleBufferA[gActiveBattler][2] << 8);
    u8 multihit = gBattleBufferA[gActiveBattler][11];

    switch (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState)
    {
    case 0:
        if (gBattleSpritesDataPtr->battlerData[gActiveBattler].behindSubstitute
            && !gBattleSpritesDataPtr->battlerData[gActiveBattler].flag_x8)
        {
            gBattleSpritesDataPtr->battlerData[gActiveBattler].flag_x8 = 1;
            InitAndLaunchSpecialAnimation(gActiveBattler, gActiveBattler, gActiveBattler, B_ANIM_SUBSTITUTE_TO_MON);
        }
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 1;
        break;
    case 1:
        if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].specialAnimActive)
        {
            SetBattlerSpriteAffineMode(ST_OAM_AFFINE_OFF);
            DoMoveAnim(move);
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 2;
        }
        break;
    case 2:
        gAnimScriptCallback();
        if (!gAnimScriptActive)
        {
            SetBattlerSpriteAffineMode(ST_OAM_AFFINE_NORMAL);
            if (gBattleSpritesDataPtr->battlerData[gActiveBattler].behindSubstitute && multihit < 2)
            {
                InitAndLaunchSpecialAnimation(gActiveBattler, gActiveBattler, gActiveBattler, B_ANIM_MON_TO_SUBSTITUTE);
                gBattleSpritesDataPtr->battlerData[gActiveBattler].flag_x8 = 0;
            }
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 3;
        }
        break;
    case 3:
        if (!gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].specialAnimActive)
        {
            CopyAllBattleSpritesInvisibilities();
            TrySetBehindSubstituteSpriteBit(gActiveBattler, gBattleBufferA[gActiveBattler][1] | (gBattleBufferA[gActiveBattler][2] << 8));
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].animationState = 0;
            OpponentBufferExecCompleted();
        }
        break;
    }
}

static void OpponentHandlePrintString(void)
{
    u16 *stringId;

    gBattle_BG0_X = 0;
    gBattle_BG0_Y = 0;
    stringId = (u16 *)(&gBattleBufferA[gActiveBattler][2]);
    BufferStringBattle(*stringId);
    BattlePutTextOnWindow(gDisplayedStringBattle, B_WIN_MSG);
    gBattlerControllerFuncs[gActiveBattler] = CompleteOnInactiveTextPrinter;
    BattleArena_DeductSkillPoints(gActiveBattler, *stringId);
}

static void OpponentHandlePrintSelectionString(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleChooseAction(void)
{
#ifdef REMOTE_OPPONENT_LEADER
    // Remote opponent mode: allow the linked follower to pick between FIGHT and SWITCH.
    // If remote isn't ready (or no reply), fall back to vanilla AI.
    if (!(gBattleTypeFlags & (BATTLE_TYPE_LINK | BATTLE_TYPE_RECORDED | BATTLE_TYPE_RECORDED_LINK)))
    {
        struct RemoteOppWaitState *state = &sRemoteOppActionState[gActiveBattler];

        // Bundled doubles protocol: only the left opponent battler talks to the follower.
        // The right opponent battler must not consume link packets or bump seq; it waits
        // until the left battler caches its decision.
        if ((gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
         && !(gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_TOWER_LINK_MULTI))
         && ((gActiveBattler & BIT_FLANK) != B_FLANK_LEFT))
        {
            u8 partnerBattler = GetBattlerAtPosition(BATTLE_PARTNER(GetBattlerPosition(gActiveBattler)));
            if (!(gAbsentBattlerFlags & gBitTable[partnerBattler])
             && !(gBattleStruct->absentBattlerFlags & gBitTable[partnerBattler]))
            {
                state->expectedSeq = sRemoteOppSeq;
                state->connectTimeout = 0;
                state->responseTimeout = 0;
                state->requestSent = TRUE;
                state->bundledSendStage = 0;
                state->lastVBlank = gMain.vblankCounter1;

                sRemoteOppFallbackToAI[gActiveBattler] = (gBattleTypeFlags & (BATTLE_TYPE_TRAINER | BATTLE_TYPE_FIRST_BATTLE | BATTLE_TYPE_SAFARI | BATTLE_TYPE_ROAMER | BATTLE_TYPE_EREADER_TRAINER)) != 0;

                RemoteOpponent_OpenLinkIfNeeded();
                gBattlerControllerFuncs[gActiveBattler] = OpponentHandleChooseAction_RemoteWaitBundledPartner;
                return;
            }
        }

        sRemoteOppSeq++;
        state->expectedSeq = sRemoteOppSeq;
        state->connectTimeout = 0;
        state->responseTimeout = 0;
        state->requestSent = FALSE;
        state->bundledSendStage = 0;
        state->lastVBlank = gMain.vblankCounter1;

        // If remote doesn't respond, decide whether we should fall back to AI (trainers)
        // or default to fighting (most wild battles). Keep this consistent with move flow.
        sRemoteOppFallbackToAI[gActiveBattler] = (gBattleTypeFlags & (BATTLE_TYPE_TRAINER | BATTLE_TYPE_FIRST_BATTLE | BATTLE_TYPE_SAFARI | BATTLE_TYPE_ROAMER | BATTLE_TYPE_EREADER_TRAINER)) != 0;

        RemoteOpponent_OpenLinkIfNeeded();
        gBattlerControllerFuncs[gActiveBattler] = OpponentHandleChooseAction_RemoteWait;
        return;
    }
#endif

    AI_TrySwitchOrUseItem();
    OpponentBufferExecCompleted();
}

#ifdef REMOTE_OPPONENT_LEADER
static void BuildRemoteOppPartyInfo(struct RemoteOpponentPartyInfo *outParty);
static bool8 IsValidRemoteOppSwitchSlot(const struct RemoteOpponentPartyInfo *party, u8 slot);

static void RemoteOpp_ApplyDecision(u8 action, u8 param1, u8 param2, u8 partnerBattler, u8 expectedSeq)
{
    if (action == REMOTE_OPP_ACTION_CANCEL_PARTNER)
    {
        // Only meaningful for the second battler in doubles.
        if ((gBattleTypeFlags & BATTLE_TYPE_DOUBLE) && ((gActiveBattler & BIT_FLANK) != B_FLANK_LEFT))
        {
            // Clear cached move decisions since the player is re-choosing.
            sRemoteOppHasPendingMoveDecision[gActiveBattler] = FALSE;
            sRemoteOppHasPendingMoveDecision[partnerBattler] = FALSE;
            sRemoteOppHasPendingDecision[gActiveBattler] = FALSE;
            sRemoteOppHasPendingDecision[partnerBattler] = FALSE;

            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_CANCEL_PARTNER, 0);
            OpponentBufferExecCompleted();
            return;
        }
        // Otherwise ignore and fall through to default behavior.
    }

    if (action == REMOTE_OPP_ACTION_SWITCH)
    {
        // Party may have changed due to prior events; rebuild for validation.
        BuildRemoteOppPartyInfo(&sRemoteOppParty[gActiveBattler]);
        // Ensure no stale cached move decision survives if we end up switching.
        sRemoteOppHasPendingMoveDecision[gActiveBattler] = FALSE;
        if (IsValidRemoteOppSwitchSlot(&sRemoteOppParty[gActiveBattler], param1))
        {
            *(gBattleStruct->AI_monToSwitchIntoId + gActiveBattler) = param1;
            *(gBattleStruct->monToSwitchIntoId + gActiveBattler) = param1;

            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_SWITCH, 0);
            OpponentBufferExecCompleted();
            return;
        }
    }

    if (action == REMOTE_OPP_ACTION_ITEM)
    {
        u16 item;
        const u8 *itemEffect;

        // Ensure no stale cached move decision survives if we end up using an item.
        sRemoteOppHasPendingMoveDecision[gActiveBattler] = FALSE;

        if (gBattleResources != NULL && gBattleResources->battleHistory != NULL
         && param1 < MAX_TRAINER_ITEMS)
        {
            item = gBattleResources->battleHistory->trainerItems[param1];
            if (item != ITEM_NONE && item >= ITEM_POTION)
            {
                if (gItemEffectTable[item - ITEM_POTION] == NULL)
                    itemEffect = NULL;
                else
                    itemEffect = gItemEffectTable[item - ITEM_POTION];

                *(gBattleStruct->AI_itemType + (gActiveBattler / 2)) = GetRemoteOppAiItemType(item, itemEffect);

                if (*(gBattleStruct->AI_itemType + (gActiveBattler / 2)) == AI_ITEM_CURE_CONDITION
                 || item == ITEM_FULL_RESTORE)
                {
                    *(gBattleStruct->AI_itemFlags + (gActiveBattler / 2)) = GetRemoteOppAiHealFlags(item, itemEffect, gActiveBattler);
                }
                else if (*(gBattleStruct->AI_itemType + (gActiveBattler / 2)) == AI_ITEM_X_STAT)
                {
                    *(gBattleStruct->AI_itemFlags + (gActiveBattler / 2)) = GetRemoteOppAiXStatFlags(itemEffect);
                }
                else
                {
                    *(gBattleStruct->AI_itemFlags + (gActiveBattler / 2)) = 0;
                }

                *(gBattleStruct->chosenItem + (gActiveBattler / 2) * 2) = item;
                gBattleResources->battleHistory->trainerItems[param1] = ITEM_NONE;

                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_USE_ITEM, 0);
                OpponentBufferExecCompleted();
                return;
            }
        }

        // Invalid selection: default to fight so we don't deadlock.
        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_USE_MOVE, 0);
        OpponentBufferExecCompleted();
        return;
    }

    if (action == REMOTE_OPP_ACTION_FIGHT)
    {
        // Stash the chosen move + target so the later CHOOSE_MOVE controller call
        // completes locally without any additional link messages.
        sRemoteOppHasPendingMoveDecision[gActiveBattler] = TRUE;
        sRemoteOppPendingMoveSeq[gActiveBattler] = expectedSeq;
        sRemoteOppPendingMoveSlot[gActiveBattler] = param1;
        sRemoteOppPendingTargetBattler[gActiveBattler] = param2;

        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_USE_MOVE, 0);
        OpponentBufferExecCompleted();
        return;
    }

    // Default: fight.
    BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_USE_MOVE, 0);
    OpponentBufferExecCompleted();
}

static void OpponentHandleChooseAction_RemoteWaitBundledPartner(void)
{
    u8 action;
    u8 param1;
    u8 param2;
    struct RemoteOppWaitState *state = &sRemoteOppActionState[gActiveBattler];
    u8 partnerBattler = GetBattlerAtPosition(BATTLE_PARTNER(GetBattlerPosition(gActiveBattler)));

    RemoteOpponent_OpenLinkIfNeeded();

    if (gMain.vblankCounter1 != state->lastVBlank)
    {
        state->lastVBlank = gMain.vblankCounter1;
        state->responseTimeout++;
    }

    if (sRemoteOppHasPendingDecision[gActiveBattler])
    {
        sRemoteOppHasPendingDecision[gActiveBattler] = FALSE;
        action = sRemoteOppPendingDecisionAction[gActiveBattler];
        param1 = sRemoteOppPendingDecisionParam1[gActiveBattler];
        param2 = sRemoteOppPendingDecisionParam2[gActiveBattler];

        RemoteOpp_ApplyDecision(action, param1, param2, partnerBattler, state->expectedSeq);
        return;
    }

    if (state->responseTimeout > 3600)
    {
        if (sRemoteOppFallbackToAI[gActiveBattler])
            AI_TrySwitchOrUseItem();
        else
            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_USE_MOVE, 0);
        OpponentBufferExecCompleted();
        return;
    }
}

static void BuildRemoteOppPartyInfo(struct RemoteOpponentPartyInfo *outParty)
{
    s32 i;
    s32 firstId = 0;
    s32 lastId = PARTY_SIZE;
    u8 battlerIdentity = GetBattlerPosition(gActiveBattler);
    u8 partnerBattler = gActiveBattler;

    // Determine the party half-range for multi-opponent battles.
    if (gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_TOWER_LINK_MULTI))
    {
        if ((gActiveBattler & BIT_FLANK) == B_FLANK_LEFT)
            firstId = 0, lastId = PARTY_SIZE / 2;
        else
            firstId = PARTY_SIZE / 2, lastId = PARTY_SIZE;
    }

    // Current/partner party slots for disallowing invalid switches.
    if (gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
        partnerBattler = GetBattlerAtPosition(BATTLE_PARTNER(battlerIdentity));

    outParty->firstMonId = firstId;
    outParty->lastMonId = lastId;
    outParty->currentMonId = gBattlerPartyIndexes[gActiveBattler];
    if ((gAbsentBattlerFlags & gBitTable[partnerBattler])
     || (gBattleStruct->absentBattlerFlags & gBitTable[partnerBattler]))
        outParty->partnerMonId = PARTY_SIZE;
    else
        outParty->partnerMonId = gBattlerPartyIndexes[partnerBattler];

    for (i = 0; i < PARTY_SIZE; i++)
    {
        struct RemoteOpponentMonInfo *dst = &outParty->mons[i];
        dst->species = GetMonData(&gEnemyParty[i], MON_DATA_SPECIES);
        dst->hp = GetMonData(&gEnemyParty[i], MON_DATA_HP);
        dst->maxHp = GetMonData(&gEnemyParty[i], MON_DATA_MAX_HP);
        dst->status1 = GetMonData(&gEnemyParty[i], MON_DATA_STATUS);
        dst->level = GetMonData(&gEnemyParty[i], MON_DATA_LEVEL);
        GetMonData(&gEnemyParty[i], MON_DATA_NICKNAME, dst->nickname);
        dst->nickname[POKEMON_NAME_LENGTH] = EOS;
    }
}

static bool8 IsValidRemoteOppSwitchSlot(const struct RemoteOpponentPartyInfo *party, u8 slot)
{
    if (slot >= PARTY_SIZE)
        return FALSE;
    if (slot < party->firstMonId || slot >= party->lastMonId)
        return FALSE;
    if (slot == party->currentMonId || slot == party->partnerMonId)
        return FALSE;
    if (GetMonData(&gEnemyParty[slot], MON_DATA_HP) == 0)
        return FALSE;
    return TRUE;
}

static void OpponentHandleChooseAction_RemoteWait(void)
{
    u8 action;
    u8 param1;
    u8 param2;
    struct RemoteOppWaitState *state = &sRemoteOppActionState[gActiveBattler];
    u8 partnerBattler;
    bool8 canBundleDouble;

    RemoteOpponent_OpenLinkIfNeeded();

    // If we already received a bundled double-decision response earlier this turn,
    // consume the cached decision immediately (no additional link traffic).
    if (sRemoteOppHasPendingDecision[gActiveBattler])
    {
        sRemoteOppHasPendingDecision[gActiveBattler] = FALSE;
        action = sRemoteOppPendingDecisionAction[gActiveBattler];
        param1 = sRemoteOppPendingDecisionParam1[gActiveBattler];
        param2 = sRemoteOppPendingDecisionParam2[gActiveBattler];
        RemoteOpp_ApplyDecision(action, param1, param2, GetBattlerAtPosition(BATTLE_PARTNER(GetBattlerPosition(gActiveBattler))), state->expectedSeq);
        return;
    }

    partnerBattler = GetBattlerAtPosition(BATTLE_PARTNER(GetBattlerPosition(gActiveBattler)));
    canBundleDouble = (gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
        && !(gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_TOWER_LINK_MULTI))
        && ((gActiveBattler & BIT_FLANK) == B_FLANK_LEFT)
        && !(gAbsentBattlerFlags & gBitTable[partnerBattler])
        && !(gBattleStruct->absentBattlerFlags & gBitTable[partnerBattler]);

    if (gMain.vblankCounter1 != state->lastVBlank)
    {
        state->lastVBlank = gMain.vblankCounter1;
        if (!RemoteOpponent_IsReady())
            state->connectTimeout++;
        else if (state->requestSent || state->bundledSendStage != 0)
            state->responseTimeout++;
    }

    if (!RemoteOpponent_IsReady())
    {
        if (state->connectTimeout > 3600)
            goto fallback;
        return;
    }

    if (!state->requestSent)
    {
        u8 i;
        u8 playerLeft;
        u8 playerRight;
        u8 playerBattler;

        BuildRemoteOppPartyInfo(&sRemoteOppParty[gActiveBattler]);

        // Include minimal battle HUD info (enemy + player mons) for the follower action menu.
        {
            u8 battler;

            playerLeft = GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);
            playerRight = GetBattlerAtPosition(B_POSITION_PLAYER_RIGHT);

            // Controlled mon info for one (singles) or both (doubles) opponent battlers.
            for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
            {
                if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                    continue;

                sRemoteOppControlledMon[battler].species = gBattleMons[battler].species;
                sRemoteOppControlledMon[battler].hp = gBattleMons[battler].hp;
                sRemoteOppControlledMon[battler].maxHp = gBattleMons[battler].maxHP;
                sRemoteOppControlledMon[battler].status1 = gBattleMons[battler].status1;
                sRemoteOppControlledMon[battler].level = gBattleMons[battler].level;
                StringCopyN(sRemoteOppControlledMon[battler].nickname, gBattleMons[battler].nickname, POKEMON_NAME_LENGTH);
                sRemoteOppControlledMon[battler].nickname[POKEMON_NAME_LENGTH] = EOS;
            }

            if (!(gAbsentBattlerFlags & gBitTable[playerLeft]))
            {
                u8 battler;
                for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
                {
                    if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                        continue;
                    sRemoteOppTargetBattlerLeft[battler] = playerLeft;
                    sRemoteOppTargetMonLeft[battler].species = gBattleMons[playerLeft].species;
                    sRemoteOppTargetMonLeft[battler].hp = gBattleMons[playerLeft].hp;
                    sRemoteOppTargetMonLeft[battler].maxHp = gBattleMons[playerLeft].maxHP;
                    sRemoteOppTargetMonLeft[battler].status1 = gBattleMons[playerLeft].status1;
                    sRemoteOppTargetMonLeft[battler].level = gBattleMons[playerLeft].level;
                    StringCopyN(sRemoteOppTargetMonLeft[battler].nickname, gBattleMons[playerLeft].nickname, POKEMON_NAME_LENGTH);
                    sRemoteOppTargetMonLeft[battler].nickname[POKEMON_NAME_LENGTH] = EOS;
                }
            }
            else
            {
                u8 battler;
                for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
                {
                    if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                        continue;
                    sRemoteOppTargetBattlerLeft[battler] = 0xFF;
                    sRemoteOppTargetMonLeft[battler].species = SPECIES_NONE;
                    sRemoteOppTargetMonLeft[battler].nickname[0] = EOS;
                }
            }

            if (!(gAbsentBattlerFlags & gBitTable[playerRight]))
            {
                u8 battler;
                for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
                {
                    if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                        continue;
                    sRemoteOppTargetBattlerRight[battler] = playerRight;
                    sRemoteOppTargetMonRight[battler].species = gBattleMons[playerRight].species;
                    sRemoteOppTargetMonRight[battler].hp = gBattleMons[playerRight].hp;
                    sRemoteOppTargetMonRight[battler].maxHp = gBattleMons[playerRight].maxHP;
                    sRemoteOppTargetMonRight[battler].status1 = gBattleMons[playerRight].status1;
                    sRemoteOppTargetMonRight[battler].level = gBattleMons[playerRight].level;
                    StringCopyN(sRemoteOppTargetMonRight[battler].nickname, gBattleMons[playerRight].nickname, POKEMON_NAME_LENGTH);
                    sRemoteOppTargetMonRight[battler].nickname[POKEMON_NAME_LENGTH] = EOS;
                }
            }
            else
            {
                u8 battler;
                for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
                {
                    if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                        continue;
                    sRemoteOppTargetBattlerRight[battler] = 0xFF;
                    sRemoteOppTargetMonRight[battler].species = SPECIES_NONE;
                    sRemoteOppTargetMonRight[battler].nickname[0] = EOS;
                }
            }

            // Single-target HUD fallback: first non-absent player battler.
            playerBattler = playerLeft;
            if (gAbsentBattlerFlags & gBitTable[playerBattler])
                playerBattler = playerRight;

            {
                u8 battler;
                for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
                {
                    if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                        continue;
                    sRemoteOppTargetMon[battler].species = gBattleMons[playerBattler].species;
                    sRemoteOppTargetMon[battler].hp = gBattleMons[playerBattler].hp;
                    sRemoteOppTargetMon[battler].maxHp = gBattleMons[playerBattler].maxHP;
                    sRemoteOppTargetMon[battler].status1 = gBattleMons[playerBattler].status1;
                    sRemoteOppTargetMon[battler].level = gBattleMons[playerBattler].level;
                    StringCopyN(sRemoteOppTargetMon[battler].nickname, gBattleMons[playerBattler].nickname, POKEMON_NAME_LENGTH);
                    sRemoteOppTargetMon[battler].nickname[POKEMON_NAME_LENGTH] = EOS;
                }
            }
        }

        // Provide move info up-front so the follower's move menu opens instantly.
        {
            u8 battler;
            for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
            {
                if (battler != gActiveBattler && (!canBundleDouble || battler != partnerBattler))
                    continue;
                for (i = 0; i < MAX_MON_MOVES; i++)
                {
                    u16 move = gBattleMons[battler].moves[i];
                    sRemoteOppMoveInfo[battler].moves[i] = move;
                    sRemoteOppMoveInfo[battler].currentPp[i] = gBattleMons[battler].pp[i];
                    sRemoteOppMoveInfo[battler].maxPp[i] = CalculatePPWithBonus(move, gBattleMons[battler].ppBonuses, i);
                }
                sRemoteOppMoveInfo[battler].monTypes[0] = gBattleMons[battler].types[0];
                sRemoteOppMoveInfo[battler].monTypes[1] = gBattleMons[battler].types[1];
            }
        }

        if (canBundleDouble)
        {
            // NOTE: Link blocks are size-limited, and SendBlock cannot be queued twice in one tick.
            // Send the two standard decision requests in two stages (same seq), then wait for one
            // combined response. This still avoids any mid-menu link traffic.
            if (state->bundledSendStage == 0)
            {
                if (RemoteOpponent_Leader_SendDecisionRequest2(
                        state->expectedSeq,
                        gActiveBattler,
                        &sRemoteOppControlledMon[gActiveBattler],
                        sRemoteOppTargetBattlerLeft[gActiveBattler],
                        &sRemoteOppTargetMonLeft[gActiveBattler],
                        sRemoteOppTargetBattlerRight[gActiveBattler],
                        &sRemoteOppTargetMonRight[gActiveBattler],
                        &sRemoteOppMoveInfo[gActiveBattler],
                        &sRemoteOppParty[gActiveBattler]))
                {
                    state->bundledSendStage = 1;
                    state->responseTimeout = 0;
                }
                return;
            }
            else if (state->bundledSendStage == 1)
            {
                if (RemoteOpponent_Leader_SendDecisionRequest2(
                        state->expectedSeq,
                        partnerBattler,
                        &sRemoteOppControlledMon[partnerBattler],
                        sRemoteOppTargetBattlerLeft[gActiveBattler],
                        &sRemoteOppTargetMonLeft[gActiveBattler],
                        sRemoteOppTargetBattlerRight[gActiveBattler],
                        &sRemoteOppTargetMonRight[gActiveBattler],
                        &sRemoteOppMoveInfo[partnerBattler],
                        // Use the left battler's party info; follower swaps current/partner locally.
                        &sRemoteOppParty[gActiveBattler]))
                {
                    state->bundledSendStage = 2;
                    state->requestSent = TRUE;
                    state->responseTimeout = 0;
                }
                return;
            }
        }
        else if (RemoteOpponent_Leader_SendDecisionRequest2(
                    state->expectedSeq,
                    gActiveBattler,
                    &sRemoteOppControlledMon[gActiveBattler],
                    sRemoteOppTargetBattlerLeft[gActiveBattler],
                    &sRemoteOppTargetMonLeft[gActiveBattler],
                    sRemoteOppTargetBattlerRight[gActiveBattler],
                    &sRemoteOppTargetMonRight[gActiveBattler],
                    &sRemoteOppMoveInfo[gActiveBattler],
                    &sRemoteOppParty[gActiveBattler]))
        {
            state->requestSent = TRUE;
            state->responseTimeout = 0;
        }
        return;
    }

    if (canBundleDouble)
    {
        u8 actionRight;
        u8 param1Right;
        u8 param2Right;

        if (RemoteOpponent_Leader_TryRecvDecisionChoiceDouble2(
                state->expectedSeq,
                gActiveBattler,
                partnerBattler,
                &action,
                &param1,
                &param2,
                &actionRight,
                &param1Right,
                &param2Right))
        {
            sRemoteOppHasPendingDecision[partnerBattler] = TRUE;
            sRemoteOppPendingDecisionAction[partnerBattler] = actionRight;
            sRemoteOppPendingDecisionParam1[partnerBattler] = param1Right;
            sRemoteOppPendingDecisionParam2[partnerBattler] = param2Right;
            RemoteOpp_ApplyDecision(action, param1, param2, partnerBattler, state->expectedSeq);
            return;
        }
    }
    else if (RemoteOpponent_Leader_TryRecvDecisionChoice2(state->expectedSeq, gActiveBattler, &action, &param1, &param2))
    {
        RemoteOpp_ApplyDecision(action, param1, param2, partnerBattler, state->expectedSeq);
        return;
    }

    if (state->responseTimeout > 3600)
        goto fallback;
    return;

fallback:
    if (sRemoteOppFallbackToAI[gActiveBattler])
        AI_TrySwitchOrUseItem();
    else
        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_USE_MOVE, 0);
    OpponentBufferExecCompleted();
}
#endif

static void OpponentHandleYesNoBox(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleChooseMove(void)
{
    if (gBattleTypeFlags & BATTLE_TYPE_PALACE)
    {
        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, ChooseMoveAndTargetInBattlePalace());
        OpponentBufferExecCompleted();
    }
    else
    {
        u8 chosenMoveId;
        struct ChooseMoveStruct *moveInfo = (struct ChooseMoveStruct *)(&gBattleBufferA[gActiveBattler][4]);

#ifdef REMOTE_OPPONENT_LEADER
    // Remote opponent mode: let the linked follower pick the opponent's move slot.
        // Applies to all non-link battles (so it works for trainers too).
        // If the link isn't ready (or no reply), we wait briefly (with timeouts) then fall back.
        if (!(gBattleTypeFlags & (BATTLE_TYPE_LINK | BATTLE_TYPE_RECORDED | BATTLE_TYPE_RECORDED_LINK)))
        {
            u8 i;
            u8 playerLeft;
            u8 playerRight;
            u8 playerBattler;
            struct RemoteOppWaitState *state = &sRemoteOppMoveState[gActiveBattler];

            // Fast-path: if we already received a full decision (including move+target)
            // during the action-selection phase, complete immediately with no link traffic.
            if (sRemoteOppHasPendingMoveDecision[gActiveBattler])
            {
                u16 move;
                u8 moveSlot = sRemoteOppPendingMoveSlot[gActiveBattler];
                u8 targetBattlerId = sRemoteOppPendingTargetBattler[gActiveBattler];

                sRemoteOppHasPendingMoveDecision[gActiveBattler] = FALSE;

                chosenMoveId = moveSlot & (MAX_MON_MOVES - 1);
                move = moveInfo->moves[chosenMoveId];

                // Safety: if follower picked an empty slot, fall back to a valid random move.
                if (move == MOVE_NONE)
                {
                    do
                    {
                        chosenMoveId = MOD(Random(), MAX_MON_MOVES);
                        move = moveInfo->moves[chosenMoveId];
                    } while (move == MOVE_NONE);
                }

                {
                    u8 chosenTarget;
                    u8 left = sRemoteOppTargetBattlerLeft[gActiveBattler];
                    u8 right = sRemoteOppTargetBattlerRight[gActiveBattler];
                    bool8 leftValid = (left != 0xFF) && (sRemoteOppTargetMonLeft[gActiveBattler].species != SPECIES_NONE) && !(gAbsentBattlerFlags & gBitTable[left]);
                    bool8 rightValid = (right != 0xFF) && (sRemoteOppTargetMonRight[gActiveBattler].species != SPECIES_NONE) && !(gAbsentBattlerFlags & gBitTable[right]);

                    if (gBattleMoves[move].target & (MOVE_TARGET_USER_OR_SELECTED | MOVE_TARGET_USER))
                        chosenTarget = gActiveBattler;
                    else if (gBattleMoves[move].target & MOVE_TARGET_BOTH)
                        chosenTarget = leftValid ? left : right;
                    else if (gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
                    {
                        chosenTarget = targetBattlerId;
                        if (!((chosenTarget == left && leftValid) || (chosenTarget == right && rightValid)))
                            chosenTarget = leftValid ? left : rightValid ? right : GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);
                    }
                    else
                        chosenTarget = GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);

                    BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (chosenTarget << 8));
                }

                OpponentBufferExecCompleted();
                return;
            }

            // Moves + PP snapshot from the controller payload.
            for (i = 0; i < MAX_MON_MOVES; i++)
            {
                sRemoteOppMoveInfo[gActiveBattler].moves[i] = moveInfo->moves[i];
                sRemoteOppMoveInfo[gActiveBattler].currentPp[i] = moveInfo->currentPp[i];
                sRemoteOppMoveInfo[gActiveBattler].maxPp[i] = moveInfo->maxPp[i];
            }
            sRemoteOppMoveInfo[gActiveBattler].monTypes[0] = moveInfo->monTypes[0];
            sRemoteOppMoveInfo[gActiveBattler].monTypes[1] = moveInfo->monTypes[1];

            // Controlled battler (the one choosing a move).
            sRemoteOppControlledMon[gActiveBattler].species = gBattleMons[gActiveBattler].species;
            sRemoteOppControlledMon[gActiveBattler].hp = gBattleMons[gActiveBattler].hp;
            sRemoteOppControlledMon[gActiveBattler].maxHp = gBattleMons[gActiveBattler].maxHP;
            sRemoteOppControlledMon[gActiveBattler].status1 = gBattleMons[gActiveBattler].status1;
            sRemoteOppControlledMon[gActiveBattler].level = gBattleMons[gActiveBattler].level;
            StringCopyN(sRemoteOppControlledMon[gActiveBattler].nickname, gBattleMons[gActiveBattler].nickname, POKEMON_NAME_LENGTH);
            sRemoteOppControlledMon[gActiveBattler].nickname[POKEMON_NAME_LENGTH] = EOS;

            // Target candidates (for doubles target selection): player left + player right.
            playerLeft = GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);
            playerRight = GetBattlerAtPosition(B_POSITION_PLAYER_RIGHT);

            if (!(gAbsentBattlerFlags & gBitTable[playerLeft]))
            {
                sRemoteOppTargetBattlerLeft[gActiveBattler] = playerLeft;
                sRemoteOppTargetMonLeft[gActiveBattler].species = gBattleMons[playerLeft].species;
                sRemoteOppTargetMonLeft[gActiveBattler].hp = gBattleMons[playerLeft].hp;
                sRemoteOppTargetMonLeft[gActiveBattler].maxHp = gBattleMons[playerLeft].maxHP;
                sRemoteOppTargetMonLeft[gActiveBattler].status1 = gBattleMons[playerLeft].status1;
                sRemoteOppTargetMonLeft[gActiveBattler].level = gBattleMons[playerLeft].level;
                StringCopyN(sRemoteOppTargetMonLeft[gActiveBattler].nickname, gBattleMons[playerLeft].nickname, POKEMON_NAME_LENGTH);
                sRemoteOppTargetMonLeft[gActiveBattler].nickname[POKEMON_NAME_LENGTH] = EOS;
            }
            else
            {
                sRemoteOppTargetBattlerLeft[gActiveBattler] = 0xFF;
                sRemoteOppTargetMonLeft[gActiveBattler].species = SPECIES_NONE;
                sRemoteOppTargetMonLeft[gActiveBattler].nickname[0] = EOS;
            }

            if (!(gAbsentBattlerFlags & gBitTable[playerRight]))
            {
                sRemoteOppTargetBattlerRight[gActiveBattler] = playerRight;
                sRemoteOppTargetMonRight[gActiveBattler].species = gBattleMons[playerRight].species;
                sRemoteOppTargetMonRight[gActiveBattler].hp = gBattleMons[playerRight].hp;
                sRemoteOppTargetMonRight[gActiveBattler].maxHp = gBattleMons[playerRight].maxHP;
                sRemoteOppTargetMonRight[gActiveBattler].status1 = gBattleMons[playerRight].status1;
                sRemoteOppTargetMonRight[gActiveBattler].level = gBattleMons[playerRight].level;
                StringCopyN(sRemoteOppTargetMonRight[gActiveBattler].nickname, gBattleMons[playerRight].nickname, POKEMON_NAME_LENGTH);
                sRemoteOppTargetMonRight[gActiveBattler].nickname[POKEMON_NAME_LENGTH] = EOS;
            }
            else
            {
                sRemoteOppTargetBattlerRight[gActiveBattler] = 0xFF;
                sRemoteOppTargetMonRight[gActiveBattler].species = SPECIES_NONE;
                sRemoteOppTargetMonRight[gActiveBattler].nickname[0] = EOS;
            }

            // Target display (for HUD): show the first non-absent player battler.
            playerBattler = playerLeft;
            if (gAbsentBattlerFlags & gBitTable[playerBattler])
                playerBattler = playerRight;

            sRemoteOppTargetMon[gActiveBattler].species = gBattleMons[playerBattler].species;
            sRemoteOppTargetMon[gActiveBattler].hp = gBattleMons[playerBattler].hp;
            sRemoteOppTargetMon[gActiveBattler].maxHp = gBattleMons[playerBattler].maxHP;
            sRemoteOppTargetMon[gActiveBattler].status1 = gBattleMons[playerBattler].status1;
            sRemoteOppTargetMon[gActiveBattler].level = gBattleMons[playerBattler].level;
            StringCopyN(sRemoteOppTargetMon[gActiveBattler].nickname, gBattleMons[playerBattler].nickname, POKEMON_NAME_LENGTH);
            sRemoteOppTargetMon[gActiveBattler].nickname[POKEMON_NAME_LENGTH] = EOS;

            // For battle types that normally use trainer AI here, preserve that behavior
            // as the fallback path (instead of random wild logic).
            sRemoteOppFallbackToAI[gActiveBattler] = (gBattleTypeFlags & (BATTLE_TYPE_TRAINER | BATTLE_TYPE_FIRST_BATTLE | BATTLE_TYPE_SAFARI | BATTLE_TYPE_ROAMER | BATTLE_TYPE_EREADER_TRAINER)) != 0;

            sRemoteOppSeq++;
            state->expectedSeq = sRemoteOppSeq;
            state->bundledSendStage = 0;
            state->connectTimeout = 0;
            state->responseTimeout = 0;
            state->requestSent = FALSE;
            state->lastVBlank = gMain.vblankCounter1;

            RemoteOpponent_OpenLinkIfNeeded();
            gBattlerControllerFuncs[gActiveBattler] = OpponentHandleChooseMove_RemoteWait;
            return;
        }
#endif

        if (gBattleTypeFlags & (BATTLE_TYPE_TRAINER | BATTLE_TYPE_FIRST_BATTLE | BATTLE_TYPE_SAFARI | BATTLE_TYPE_ROAMER))
        {

            BattleAI_SetupAIData(ALL_MOVES_MASK);
            chosenMoveId = BattleAI_ChooseMoveOrAction();

            switch (chosenMoveId)
            {
            case AI_CHOICE_WATCH:
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_SAFARI_WATCH_CAREFULLY, 0);
                break;
            case AI_CHOICE_FLEE:
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_RUN, 0);
                break;
            case 6:
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 15, gBattlerTarget);
                break;
            default:
                if (gBattleMoves[moveInfo->moves[chosenMoveId]].target & (MOVE_TARGET_USER_OR_SELECTED | MOVE_TARGET_USER))
                    gBattlerTarget = gActiveBattler;
                if (gBattleMoves[moveInfo->moves[chosenMoveId]].target & MOVE_TARGET_BOTH)
                {
                    gBattlerTarget = GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);
                    if (gAbsentBattlerFlags & gBitTable[gBattlerTarget])
                        gBattlerTarget = GetBattlerAtPosition(B_POSITION_PLAYER_RIGHT);
                }
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (gBattlerTarget << 8));
                break;
            }
            OpponentBufferExecCompleted();
        }
        else
        {
            u16 move;
            do
            {
                chosenMoveId = MOD(Random(), MAX_MON_MOVES);
                move = moveInfo->moves[chosenMoveId];
            } while (move == MOVE_NONE);

            if (gBattleMoves[move].target & (MOVE_TARGET_USER_OR_SELECTED | MOVE_TARGET_USER))
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (gActiveBattler << 8));
            else if (gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (GetBattlerAtPosition(Random() & 2) << 8));
            else
                BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (GetBattlerAtPosition(B_POSITION_PLAYER_LEFT) << 8));

            OpponentBufferExecCompleted();
        }
    }
}

#ifdef REMOTE_OPPONENT_LEADER
static void OpponentHandleChooseMove_RemoteWait(void)
{
    u8 chosenMoveId;
    u16 move;
    u8 moveSlot;
    u8 targetBattlerId;
    struct ChooseMoveStruct *moveInfo = (struct ChooseMoveStruct *)(&gBattleBufferA[gActiveBattler][4]);
    struct RemoteOppWaitState *state = &sRemoteOppMoveState[gActiveBattler];

    RemoteOpponent_OpenLinkIfNeeded();

    // The battle engine may call battler controller funcs multiple times per frame.
    // Make timeouts advance once per frame (VBlank) to avoid burning through them instantly.
    if (gMain.vblankCounter1 != state->lastVBlank)
    {
        state->lastVBlank = gMain.vblankCounter1;
        if (!RemoteOpponent_IsReady())
            state->connectTimeout++;
        else if (state->requestSent)
            state->responseTimeout++;
    }

    // Phase 1: wait for link to be ready.
    // This prevents immediate fallback when the follower isn't connected yet.
    if (!RemoteOpponent_IsReady())
    {
        if (state->connectTimeout > 3600) // ~60 seconds @ 60fps
            goto fallback;
        return;
    }

    // Phase 2: send request once.
    if (!state->requestSent)
    {
        if (RemoteOpponent_Leader_SendMoveRequest(
                state->expectedSeq,
                gActiveBattler,
                &sRemoteOppControlledMon[gActiveBattler],
                sRemoteOppTargetBattlerLeft[gActiveBattler],
                &sRemoteOppTargetMonLeft[gActiveBattler],
                sRemoteOppTargetBattlerRight[gActiveBattler],
                &sRemoteOppTargetMonRight[gActiveBattler],
                &sRemoteOppMoveInfo[gActiveBattler]))
        {
            state->requestSent = TRUE;
            state->responseTimeout = 0;
        }
        return;
    }

    // Phase 3: wait for response.
    if (RemoteOpponent_Leader_TryRecvMoveChoice2(state->expectedSeq, gActiveBattler, &moveSlot, &targetBattlerId))
    {
        // Follower requested cancel/back from the move menu.
        // Use the vanilla cancel sentinel (0xFFFF) so the engine re-prompts for action.
        if (moveSlot == REMOTE_OPP_MOVE_SLOT_CANCEL)
        {
            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, 0xFFFF);
            OpponentBufferExecCompleted();
            return;
        }

        chosenMoveId = moveSlot & (MAX_MON_MOVES - 1);
        move = moveInfo->moves[chosenMoveId];

        // Safety: if follower picked an empty slot, fall back to a valid random move.
        if (move == MOVE_NONE)
        {
            do
            {
                chosenMoveId = MOD(Random(), MAX_MON_MOVES);
                move = moveInfo->moves[chosenMoveId];
            } while (move == MOVE_NONE);
        }

        {
            u8 chosenTarget;
            u8 left = sRemoteOppTargetBattlerLeft[gActiveBattler];
            u8 right = sRemoteOppTargetBattlerRight[gActiveBattler];
            bool8 leftValid = (left != 0xFF) && (sRemoteOppTargetMonLeft[gActiveBattler].species != SPECIES_NONE) && !(gAbsentBattlerFlags & gBitTable[left]);
            bool8 rightValid = (right != 0xFF) && (sRemoteOppTargetMonRight[gActiveBattler].species != SPECIES_NONE) && !(gAbsentBattlerFlags & gBitTable[right]);

            if (gBattleMoves[move].target & (MOVE_TARGET_USER_OR_SELECTED | MOVE_TARGET_USER))
                chosenTarget = gActiveBattler;
            else if (gBattleMoves[move].target & MOVE_TARGET_BOTH)
                chosenTarget = leftValid ? left : right;
            else if (gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
            {
                chosenTarget = targetBattlerId;
                if (!((chosenTarget == left && leftValid) || (chosenTarget == right && rightValid)))
                    chosenTarget = leftValid ? left : rightValid ? right : GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);
            }
            else
                chosenTarget = GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);

            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (chosenTarget << 8));
        }

        OpponentBufferExecCompleted();
        return;
    }

    // Timeout waiting for response -> fallback to vanilla random move.
    if (state->responseTimeout > 3600) // ~60 seconds @ 60fps
        goto fallback;
    return;

fallback:
    if (sRemoteOppFallbackToAI[gActiveBattler])
    {
        // Preserve the vanilla AI path for battle types that expect it.
        BattleAI_SetupAIData(ALL_MOVES_MASK);
        chosenMoveId = BattleAI_ChooseMoveOrAction();

        switch (chosenMoveId)
        {
        case AI_CHOICE_WATCH:
            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_SAFARI_WATCH_CAREFULLY, 0);
            break;
        case AI_CHOICE_FLEE:
            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, B_ACTION_RUN, 0);
            break;
        case 6:
            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 15, gBattlerTarget);
            break;
        default:
            if (gBattleMoves[moveInfo->moves[chosenMoveId]].target & (MOVE_TARGET_USER_OR_SELECTED | MOVE_TARGET_USER))
                gBattlerTarget = gActiveBattler;
            if (gBattleMoves[moveInfo->moves[chosenMoveId]].target & MOVE_TARGET_BOTH)
            {
                gBattlerTarget = GetBattlerAtPosition(B_POSITION_PLAYER_LEFT);
                if (gAbsentBattlerFlags & gBitTable[gBattlerTarget])
                    gBattlerTarget = GetBattlerAtPosition(B_POSITION_PLAYER_RIGHT);
            }
            BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (gBattlerTarget << 8));
            break;
        }

        OpponentBufferExecCompleted();
        return;
    }

    do
    {
        chosenMoveId = MOD(Random(), MAX_MON_MOVES);
        move = moveInfo->moves[chosenMoveId];
    } while (move == MOVE_NONE);

    if (gBattleMoves[move].target & (MOVE_TARGET_USER_OR_SELECTED | MOVE_TARGET_USER))
        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (gActiveBattler << 8));
    else if (gBattleTypeFlags & BATTLE_TYPE_DOUBLE)
        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (GetBattlerAtPosition(Random() & 2) << 8));
    else
        BtlController_EmitTwoReturnValues(B_COMM_TO_ENGINE, 10, (chosenMoveId) | (GetBattlerAtPosition(B_POSITION_PLAYER_LEFT) << 8));

    OpponentBufferExecCompleted();
    return;
}
#endif

static void OpponentHandleChooseItem(void)
{
    BtlController_EmitOneReturnValue(B_COMM_TO_ENGINE, *(gBattleStruct->chosenItem + (gActiveBattler / 2) * 2));
    OpponentBufferExecCompleted();
}

static void OpponentHandleChoosePokemon(void)
{
    s32 chosenMonId;

    if (*(gBattleStruct->AI_monToSwitchIntoId + gActiveBattler) == PARTY_SIZE)
    {
        chosenMonId = GetMostSuitableMonToSwitchInto();

        if (chosenMonId == PARTY_SIZE)
        {
            s32 battler1, battler2, firstId, lastId;

            if (!(gBattleTypeFlags & BATTLE_TYPE_DOUBLE))
            {
                battler2 = battler1 = GetBattlerAtPosition(B_POSITION_OPPONENT_LEFT);
            }
            else
            {
                battler1 = GetBattlerAtPosition(B_POSITION_OPPONENT_LEFT);
                battler2 = GetBattlerAtPosition(B_POSITION_OPPONENT_RIGHT);
            }

            if (gBattleTypeFlags & (BATTLE_TYPE_TWO_OPPONENTS | BATTLE_TYPE_TOWER_LINK_MULTI))
            {
                if (gActiveBattler == 1)
                    firstId = 0, lastId = PARTY_SIZE / 2;
                else
                    firstId = PARTY_SIZE / 2, lastId = PARTY_SIZE;
            }
            else
            {
                firstId = 0, lastId = PARTY_SIZE;
            }

            for (chosenMonId = firstId; chosenMonId < lastId; chosenMonId++)
            {
                if (GetMonData(&gEnemyParty[chosenMonId], MON_DATA_HP) != 0
                    && chosenMonId != gBattlerPartyIndexes[battler1]
                    && chosenMonId != gBattlerPartyIndexes[battler2])
                {
                    break;
                }
            }
        }
    }
    else
    {
        chosenMonId = *(gBattleStruct->AI_monToSwitchIntoId + gActiveBattler);
        *(gBattleStruct->AI_monToSwitchIntoId + gActiveBattler) = PARTY_SIZE;
    }


    *(gBattleStruct->monToSwitchIntoId + gActiveBattler) = chosenMonId;
    BtlController_EmitChosenMonReturnValue(B_COMM_TO_ENGINE, chosenMonId, NULL);
    OpponentBufferExecCompleted();
}

static void OpponentHandleCmd23(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleHealthBarUpdate(void)
{
    s16 hpVal;

    LoadBattleBarGfx(0);
    hpVal = (gBattleBufferA[gActiveBattler][3] << 8) | gBattleBufferA[gActiveBattler][2];

    if (hpVal != INSTANT_HP_BAR_DROP)
    {
        u32 maxHP = GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_MAX_HP);
        u32 curHP = GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_HP);

        SetBattleBarStruct(gActiveBattler, gHealthboxSpriteIds[gActiveBattler], maxHP, curHP, hpVal);
    }
    else
    {
        u32 maxHP = GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_MAX_HP);

        SetBattleBarStruct(gActiveBattler, gHealthboxSpriteIds[gActiveBattler], maxHP, 0, hpVal);
    }

    gBattlerControllerFuncs[gActiveBattler] = CompleteOnHealthbarDone;
}

static void OpponentHandleExpUpdate(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleStatusIconUpdate(void)
{
    if (!IsBattleSEPlaying(gActiveBattler))
    {
        u8 battler;

        UpdateHealthboxAttribute(gHealthboxSpriteIds[gActiveBattler], &gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], HEALTHBOX_STATUS_ICON);
        battler = gActiveBattler;
        gBattleSpritesDataPtr->healthBoxesData[battler].statusAnimActive = 0;
        gBattlerControllerFuncs[gActiveBattler] = CompleteOnFinishedStatusAnimation;
    }
}

static void OpponentHandleStatusAnimation(void)
{
    if (!IsBattleSEPlaying(gActiveBattler))
    {
        InitAndLaunchChosenStatusAnimation(gBattleBufferA[gActiveBattler][1],
                        gBattleBufferA[gActiveBattler][2] | (gBattleBufferA[gActiveBattler][3] << 8) | (gBattleBufferA[gActiveBattler][4] << 16) | (gBattleBufferA[gActiveBattler][5] << 24));
        gBattlerControllerFuncs[gActiveBattler] = CompleteOnFinishedStatusAnimation;
    }
}

static void OpponentHandleStatusXor(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleDataTransfer(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleDMA3Transfer(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandlePlayBGM(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleCmd32(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleTwoReturnValues(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleChosenMonReturnValue(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleOneReturnValue(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleOneReturnValue_Duplicate(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleClearUnkVar(void)
{
    gUnusedControllerStruct.unk = 0;
    OpponentBufferExecCompleted();
}

static void OpponentHandleSetUnkVar(void)
{
    gUnusedControllerStruct.unk = gBattleBufferA[gActiveBattler][1];
    OpponentBufferExecCompleted();
}

static void OpponentHandleClearUnkFlag(void)
{
    gUnusedControllerStruct.flag = 0;
    OpponentBufferExecCompleted();
}

static void OpponentHandleToggleUnkFlag(void)
{
    gUnusedControllerStruct.flag ^= 1;
    OpponentBufferExecCompleted();
}

static void OpponentHandleHitAnimation(void)
{
    if (gSprites[gBattlerSpriteIds[gActiveBattler]].invisible == TRUE)
    {
        OpponentBufferExecCompleted();
    }
    else
    {
        gDoingBattleAnim = TRUE;
        gSprites[gBattlerSpriteIds[gActiveBattler]].data[1] = 0;
        DoHitAnimHealthboxEffect(gActiveBattler);
        gBattlerControllerFuncs[gActiveBattler] = DoHitAnimBlinkSpriteEffect;
    }
}

static void OpponentHandleCantSwitch(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandlePlaySE(void)
{
    s8 pan;

    if (GetBattlerSide(gActiveBattler) == B_SIDE_PLAYER)
        pan = SOUND_PAN_ATTACKER;
    else
        pan = SOUND_PAN_TARGET;

    PlaySE12WithPanning(gBattleBufferA[gActiveBattler][1] | (gBattleBufferA[gActiveBattler][2] << 8), pan);
    OpponentBufferExecCompleted();
}

static void OpponentHandlePlayFanfareOrBGM(void)
{
    if (gBattleBufferA[gActiveBattler][3])
    {
        BattleStopLowHpSound();
        PlayBGM(gBattleBufferA[gActiveBattler][1] | (gBattleBufferA[gActiveBattler][2] << 8));
    }
    else
    {
        PlayFanfare(gBattleBufferA[gActiveBattler][1] | (gBattleBufferA[gActiveBattler][2] << 8));
    }

    OpponentBufferExecCompleted();
}

static void OpponentHandleFaintingCry(void)
{
    u16 species = GetMonData(&gEnemyParty[gBattlerPartyIndexes[gActiveBattler]], MON_DATA_SPECIES);

    PlayCry_ByMode(species, 25, CRY_MODE_FAINT);
    OpponentBufferExecCompleted();
}

static void OpponentHandleIntroSlide(void)
{
    HandleIntroSlide(gBattleBufferA[gActiveBattler][1]);
    gIntroSlideFlags |= 1;
    OpponentBufferExecCompleted();
}

static void OpponentHandleIntroTrainerBallThrow(void)
{
    u8 taskId;

    SetSpritePrimaryCoordsFromSecondaryCoords(&gSprites[gBattlerSpriteIds[gActiveBattler]]);

    gSprites[gBattlerSpriteIds[gActiveBattler]].data[0] = 35;
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[2] = 280;
    gSprites[gBattlerSpriteIds[gActiveBattler]].data[4] = gSprites[gBattlerSpriteIds[gActiveBattler]].y;
    gSprites[gBattlerSpriteIds[gActiveBattler]].callback = StartAnimLinearTranslation;

    StoreSpriteCallbackInData6(&gSprites[gBattlerSpriteIds[gActiveBattler]], SpriteCB_FreeOpponentSprite);

    taskId = CreateTask(Task_StartSendOutAnim, 5);
    gTasks[taskId].data[0] = gActiveBattler;

    if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusSummaryShown)
        gTasks[gBattlerStatusSummaryTaskId[gActiveBattler]].func = Task_HidePartyStatusSummary;

    gBattleSpritesDataPtr->animationData->introAnimActive = TRUE;
    gBattlerControllerFuncs[gActiveBattler] = OpponentDummy;
}

static void SpriteCB_FreeOpponentSprite(struct Sprite *sprite)
{
    FreeTrainerFrontPicPalette(sprite->oam.affineParam);
    FreeSpriteOamMatrix(sprite);
    DestroySprite(sprite);
}

static void Task_StartSendOutAnim(u8 taskId)
{
    u8 savedActiveBank = gActiveBattler;

    gActiveBattler = gTasks[taskId].data[0];
    if (!IsDoubleBattle() || (gBattleTypeFlags & BATTLE_TYPE_MULTI))
    {
        gBattleBufferA[gActiveBattler][1] = gBattlerPartyIndexes[gActiveBattler];
        StartSendOutAnim(gActiveBattler, FALSE);
    }
    else if ((gBattleTypeFlags & BATTLE_TYPE_TWO_OPPONENTS))
    {
        gBattleBufferA[gActiveBattler][1] = gBattlerPartyIndexes[gActiveBattler];
        StartSendOutAnim(gActiveBattler, FALSE);
    }
    else
    {
        gBattleBufferA[gActiveBattler][1] = gBattlerPartyIndexes[gActiveBattler];
        StartSendOutAnim(gActiveBattler, FALSE);
        gActiveBattler ^= BIT_FLANK;
        if (!(gAbsentBattlerFlags & gBitTable[gActiveBattler]))
        {
            gBattleBufferA[gActiveBattler][1] = gBattlerPartyIndexes[gActiveBattler];
            StartSendOutAnim(gActiveBattler, FALSE);
        }
        gActiveBattler ^= BIT_FLANK;
    }
    gBattlerControllerFuncs[gActiveBattler] = Intro_TryShinyAnimShowHealthbox;
    gActiveBattler = savedActiveBank;
    DestroyTask(taskId);
}

static void OpponentHandleDrawPartyStatusSummary(void)
{
    if (gBattleBufferA[gActiveBattler][1] != 0 && GetBattlerSide(gActiveBattler) == B_SIDE_PLAYER)
    {
        OpponentBufferExecCompleted();
    }
    else
    {
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusSummaryShown = 1;

        if (gBattleBufferA[gActiveBattler][2] != 0)
        {
            if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].opponentDrawPartyStatusSummaryDelay < 2)
            {
                gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].opponentDrawPartyStatusSummaryDelay++;
                return;
            }
            else
            {
                gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].opponentDrawPartyStatusSummaryDelay = 0;
            }
        }

        gBattlerStatusSummaryTaskId[gActiveBattler] = CreatePartyStatusSummarySprites(gActiveBattler, (struct HpAndStatus *)&gBattleBufferA[gActiveBattler][4], gBattleBufferA[gActiveBattler][1], gBattleBufferA[gActiveBattler][2]);
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusDelayTimer = 0;

        if (gBattleBufferA[gActiveBattler][2] != 0)
            gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusDelayTimer = 93;

        gBattlerControllerFuncs[gActiveBattler] = EndDrawPartyStatusSummary;
    }
}

static void EndDrawPartyStatusSummary(void)
{
    if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusDelayTimer++ > 92)
    {
        gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusDelayTimer = 0;
        OpponentBufferExecCompleted();
    }
}

static void OpponentHandleHidePartyStatusSummary(void)
{
    if (gBattleSpritesDataPtr->healthBoxesData[gActiveBattler].partyStatusSummaryShown)
        gTasks[gBattlerStatusSummaryTaskId[gActiveBattler]].func = Task_HidePartyStatusSummary;
    OpponentBufferExecCompleted();
}

static void OpponentHandleEndBounceEffect(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleSpriteInvisibility(void)
{
    if (IsBattlerSpritePresent(gActiveBattler))
    {
        gSprites[gBattlerSpriteIds[gActiveBattler]].invisible = gBattleBufferA[gActiveBattler][1];
        CopyBattleSpriteInvisibility(gActiveBattler);
    }
    OpponentBufferExecCompleted();
}

static void OpponentHandleBattleAnimation(void)
{
    if (!IsBattleSEPlaying(gActiveBattler))
    {
        u8 animationId = gBattleBufferA[gActiveBattler][1];
        u16 argument = gBattleBufferA[gActiveBattler][2] | (gBattleBufferA[gActiveBattler][3] << 8);

        if (TryHandleLaunchBattleTableAnimation(gActiveBattler, gActiveBattler, gActiveBattler, animationId, argument))
            OpponentBufferExecCompleted();
        else
            gBattlerControllerFuncs[gActiveBattler] = CompleteOnFinishedBattleAnimation;
    }
}

static void OpponentHandleLinkStandbyMsg(void)
{
    OpponentBufferExecCompleted();
}

static void OpponentHandleResetActionMoveSelection(void)
{
#ifdef REMOTE_OPPONENT_LEADER
    u8 battler;
    for (battler = 0; battler < MAX_BATTLERS_COUNT; battler++)
    {
        sRemoteOppHasPendingDecision[battler] = FALSE;
        sRemoteOppHasPendingMoveDecision[battler] = FALSE;
    }
#endif
    OpponentBufferExecCompleted();
}

static void OpponentHandleEndLinkBattle(void)
{
    if (gBattleTypeFlags & BATTLE_TYPE_LINK && !(gBattleTypeFlags & BATTLE_TYPE_IS_MASTER))
    {
        gMain.inBattle = FALSE;
        gMain.callback1 = gPreBattleCallback1;
        SetMainCallback2(gMain.savedCallback);
    }
    OpponentBufferExecCompleted();
}

static void OpponentCmdEnd(void)
{
}
