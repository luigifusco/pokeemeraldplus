#ifndef GUARD_ITEM_H
#define GUARD_ITEM_H

#include "constants/item.h"
#include "constants/items.h"
#include "constants/tms_hms.h"

typedef void (*ItemUseFunc)(u8);

struct Item
{
    u8 name[ITEM_NAME_LENGTH];
    u16 itemId;
    u16 price;
    u8 holdEffect;
    u8 holdEffectParam;
    const u8 *description;
    u8 importance;
    bool8 registrability; // unused
    u8 pocket;
    u8 type;
    ItemUseFunc fieldUseFunc;
    u8 battleUsage;
    ItemUseFunc battleUseFunc;
    u8 secondaryId;
};

struct BagPocket
{
    struct ItemSlot *itemSlots;
    u8 capacity;
};

extern const struct Item gItems[];
extern struct BagPocket gBagPockets[];

void ApplyNewEncryptionKeyToBagItems(u32 newKey);
void ApplyNewEncryptionKeyToBagItems_(u32 newKey);
void SetBagItemsPointers(void);
void CopyItemName(u16 itemId, u8 *dst);
void CopyItemNameHandlePlural(u16 itemId, u8 *dst, u32 quantity);
void GetBerryCountString(u8 *dst, const u8 *berryName, u32 quantity);
bool8 IsBagPocketNonEmpty(u8 pocket);
bool8 CheckBagHasItem(u16 itemId, u16 count);
bool8 HasAtLeastOneBerry(void);
bool8 CheckBagHasSpace(u16 itemId, u16 count);
bool8 AddBagItem(u16 itemId, u16 count);
bool8 RemoveBagItem(u16 itemId, u16 count);
u8 GetPocketByItemId(u16 itemId);
void ClearItemSlots(struct ItemSlot *itemSlots, u8 itemCount);
u8 CountUsedPCItemSlots(void);
bool8 CheckPCHasItem(u16 itemId, u16 count);
bool8 AddPCItem(u16 itemId, u16 count);
void RemovePCItem(u8 index, u16 count);
void CompactPCItems(void);
void SwapRegisteredBike(void);
u16 BagGetItemIdByPocketPosition(u8 pocketId, u16 pocketPos);
u16 BagGetQuantityByPocketPosition(u8 pocketId, u16 pocketPos);
void CompactItemsInBagPocket(struct BagPocket *bagPocket);
void SortBerriesOrTMHMs(struct BagPocket *bagPocket);
void MoveItemSlotInList(struct ItemSlot *itemSlots_, u32 from, u32 to_);
void ClearBag(void);
u16 CountTotalItemQuantityInBag(u16 itemId);
bool8 AddPyramidBagItem(u16 itemId, u16 count);
bool8 RemovePyramidBagItem(u16 itemId, u16 count);
const u8 *GetItemName(u16 itemId);
u16 GetItemPrice(u16 itemId);
u8 GetItemHoldEffect(u16 itemId);
u8 GetItemHoldEffectParam(u16 itemId);
const u8 *GetItemDescription(u16 itemId);
u8 GetItemImportance(u16 itemId);
u8 GetItemPocket(u16 itemId);
u8 GetItemType(u16 itemId);
ItemUseFunc GetItemFieldFunc(u16 itemId);
u8 GetItemBattleUsage(u16 itemId);
ItemUseFunc GetItemBattleFunc(u16 itemId);
u8 GetItemSecondaryId(u16 itemId);

enum
{
    // Keep these aliases tied to the physical TM slots. FOREACH_TM may be
    // randomized to change each slot's move, but scripts and item data still
    // refer to the vanilla TM item names.
    ITEM_TM_FOCUS_PUNCH = ITEM_TM01,
    ITEM_TM_DRAGON_CLAW = ITEM_TM02,
    ITEM_TM_WATER_PULSE = ITEM_TM03,
    ITEM_TM_CALM_MIND = ITEM_TM04,
    ITEM_TM_ROAR = ITEM_TM05,
    ITEM_TM_TOXIC = ITEM_TM06,
    ITEM_TM_HAIL = ITEM_TM07,
    ITEM_TM_BULK_UP = ITEM_TM08,
    ITEM_TM_BULLET_SEED = ITEM_TM09,
    ITEM_TM_HIDDEN_POWER = ITEM_TM10,
    ITEM_TM_SUNNY_DAY = ITEM_TM11,
    ITEM_TM_TAUNT = ITEM_TM12,
    ITEM_TM_ICE_BEAM = ITEM_TM13,
    ITEM_TM_BLIZZARD = ITEM_TM14,
    ITEM_TM_HYPER_BEAM = ITEM_TM15,
    ITEM_TM_LIGHT_SCREEN = ITEM_TM16,
    ITEM_TM_PROTECT = ITEM_TM17,
    ITEM_TM_RAIN_DANCE = ITEM_TM18,
    ITEM_TM_GIGA_DRAIN = ITEM_TM19,
    ITEM_TM_SAFEGUARD = ITEM_TM20,
    ITEM_TM_FRUSTRATION = ITEM_TM21,
    ITEM_TM_SOLAR_BEAM = ITEM_TM22,
    ITEM_TM_IRON_TAIL = ITEM_TM23,
    ITEM_TM_THUNDERBOLT = ITEM_TM24,
    ITEM_TM_THUNDER = ITEM_TM25,
    ITEM_TM_EARTHQUAKE = ITEM_TM26,
    ITEM_TM_RETURN = ITEM_TM27,
    ITEM_TM_DIG = ITEM_TM28,
    ITEM_TM_PSYCHIC = ITEM_TM29,
    ITEM_TM_SHADOW_BALL = ITEM_TM30,
    ITEM_TM_BRICK_BREAK = ITEM_TM31,
    ITEM_TM_DOUBLE_TEAM = ITEM_TM32,
    ITEM_TM_REFLECT = ITEM_TM33,
    ITEM_TM_SHOCK_WAVE = ITEM_TM34,
    ITEM_TM_FLAMETHROWER = ITEM_TM35,
    ITEM_TM_SLUDGE_BOMB = ITEM_TM36,
    ITEM_TM_SANDSTORM = ITEM_TM37,
    ITEM_TM_FIRE_BLAST = ITEM_TM38,
    ITEM_TM_ROCK_TOMB = ITEM_TM39,
    ITEM_TM_AERIAL_ACE = ITEM_TM40,
    ITEM_TM_TORMENT = ITEM_TM41,
    ITEM_TM_FACADE = ITEM_TM42,
    ITEM_TM_SECRET_POWER = ITEM_TM43,
    ITEM_TM_REST = ITEM_TM44,
    ITEM_TM_ATTRACT = ITEM_TM45,
    ITEM_TM_THIEF = ITEM_TM46,
    ITEM_TM_STEEL_WING = ITEM_TM47,
    ITEM_TM_SKILL_SWAP = ITEM_TM48,
    ITEM_TM_SNATCH = ITEM_TM49,
    ITEM_TM_OVERHEAT = ITEM_TM50,

    ITEM_HM_CUT = ITEM_HM01,
    ITEM_HM_FLY = ITEM_HM02,
    ITEM_HM_SURF = ITEM_HM03,
    ITEM_HM_STRENGTH = ITEM_HM04,
    ITEM_HM_FLASH = ITEM_HM05,
    ITEM_HM_ROCK_SMASH = ITEM_HM06,
    ITEM_HM_WATERFALL = ITEM_HM07,
    ITEM_HM_DIVE = ITEM_HM08,
};

#endif // GUARD_ITEM_H
