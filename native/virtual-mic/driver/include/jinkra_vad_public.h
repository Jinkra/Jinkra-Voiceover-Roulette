#pragma once
#include <guiddef.h>
#include <stdint.h>
DEFINE_GUID(KSPROPSETID_JinkraVad,0xd06fc8a7,0xf69d,0x459f,0xa3,0x48,0x58,0x05,0xee,0x94,0x58,0xbc);
enum JINKRA_VAD_PROPERTY:uint32_t{
    JinkraVadPropertyStats=1,JinkraVadPropertyResetStats=2,
    JinkraVadPropertyVersion=3,JinkraVadPropertyLatencyMode=4,
};
enum JINKRA_VAD_LATENCY_MODE:uint32_t{
    JinkraVadLatencyUltraLow=0,JinkraVadLatencyBalanced=1,
    JinkraVadLatencyResilient=2,
};
static constexpr uint32_t JINKRA_VAD_STATS_VERSION=2;
static constexpr uint32_t JINKRA_VAD_DRIVER_ABI=3;
struct JINKRA_VAD_STATS_V2{
    uint32_t size,version;
    uint64_t write_frames,read_frames,dropped_frames,silent_frames,discarded_frames;
    uint64_t discontinuities,prime_silence_frames,fade_frames_generated,stale_trim_events;
    uint32_t fill_frames,capacity_frames,high_watermark_frames,low_watermark_frames;
    uint32_t generation,epoch,render_streams,capture_streams,render_state,capture_state;
    uint32_t primed,producer_active,consumer_active,latency_mode,last_reset_reason;
    uint32_t reserved[11];
};
struct JINKRA_VAD_VERSION_V1{
    uint32_t size,abi;uint16_t major,minor,patch,build;wchar_t name[64];
};
struct JINKRA_VAD_LATENCY_CONFIG_V1{
    uint32_t size,version,mode,reserved;
};
