#pragma once
#include "common.h"

enum JINKRA_WAVE_PIN : ULONG {
    JinkraWavePinSystem = 0,
    JinkraWavePinBridge = 1,
};

enum JINKRA_TOPOLOGY_PIN : ULONG {
    JinkraTopologyPinWave = 0,
    JinkraTopologyPinEndpoint = 1,
};

extern PCFILTER_DESCRIPTOR g_JinkraRenderWaveFilter;
extern PCFILTER_DESCRIPTOR g_JinkraCaptureWaveFilter;
extern PCFILTER_DESCRIPTOR g_JinkraRenderTopologyFilter;
extern PCFILTER_DESCRIPTOR g_JinkraCaptureTopologyFilter;
