#pragma once
#include "common.h"

NTSTATUS MdFormatFromKs(
    _In_ const KSDATAFORMAT* data_format,
    _Out_ MdPcmFormat* format) noexcept;

bool MdKsFormatSupported(
    _In_ const KSDATAFORMAT* data_format) noexcept;

extern KSDATAFORMAT_WAVEFORMATEXTENSIBLE g_JinkraFloatStereo48;
extern KSDATAFORMAT_WAVEFORMATEXTENSIBLE g_JinkraPcm16Stereo48;
extern KSDATAFORMAT_WAVEFORMATEXTENSIBLE g_JinkraPcm24Stereo48;
extern KSDATAFORMAT_WAVEFORMATEXTENSIBLE g_JinkraPcm32Stereo48;
extern KSDATAFORMAT_WAVEFORMATEXTENSIBLE g_JinkraPcm16Mono48;

extern const PKSDATAFORMAT g_JinkraSupportedFormats[];
extern const ULONG g_JinkraSupportedFormatCount;
