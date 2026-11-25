#pragma once
#include "common.h"
NTSTATUS PropertyHandler_JinkraVad(_In_ PPCPROPERTY_REQUEST request);
extern PCPROPERTY_ITEM g_JinkraVadProperties[];
extern const ULONG g_JinkraVadPropertyCount;
// DEFINE_PCAUTOMATION_TABLE_PROP emits a `const` definition, so this declaration
// must match it or MSVC reports C2373.
extern const PCAUTOMATION_TABLE g_JinkraVadAutomation;
