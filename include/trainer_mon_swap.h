#ifndef GUARD_TRAINER_MON_SWAP_H
#define GUARD_TRAINER_MON_SWAP_H

bool8 ShouldOfferTrainerMonSwap(void);
void PrepareTrainerMonSwap(void);
bool8 IsTrainerMonSwapPending(void);
void CB2_ReturnToFieldForTrainerMonSwap(void);
void SetTrainerMonSwapSelection(u8 slot);
void CB2_TrainerMonSwapSelectionMade(void);

#endif // GUARD_TRAINER_MON_SWAP_H
