EventScript_UseSurf::
#ifndef FREE_HM_MODE
	checkpartymove MOVE_SURF
	goto_if_eq VAR_RESULT, PARTY_SIZE, EventScript_EndUseSurf
	bufferpartymonnick STR_VAR_1, VAR_RESULT
	setfieldeffectargument 0, VAR_RESULT
#else
	setfieldeffectargument 0, 0
#endif
	lockall
	msgbox gText_WantToUseSurf, MSGBOX_YESNO
	goto_if_eq VAR_RESULT, NO, EventScript_ReleaseUseSurf
#ifndef FREE_HM_MODE
	msgbox gText_PlayerUsedSurf, MSGBOX_DEFAULT
#else
	closemessage
#endif
	dofieldeffect FLDEFF_USE_SURF
EventScript_ReleaseUseSurf::
	releaseall
EventScript_EndUseSurf::
	end
