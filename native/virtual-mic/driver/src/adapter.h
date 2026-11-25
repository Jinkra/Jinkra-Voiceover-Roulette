#pragma once
#include "common.h"
#include "virtual_cable.h"
#include "master_clock.h"

class JinkraAdapter {
public:
    JinkraAdapter() noexcept;
    ~JinkraAdapter();

    NTSTATUS Initialize(
        _In_ PDEVICE_OBJECT device_object,
        _In_ PIRP irp,
        _In_ PRESOURCELIST resource_list);

    static JinkraVirtualCable* Cable() noexcept;
    static JinkraMasterClock* MasterClock() noexcept;

    static void Shutdown() noexcept;

private:
    NTSTATUS InstallWave(
        _In_ PDEVICE_OBJECT device_object,
        _In_ PIRP irp,
        _In_ PRESOURCELIST resource_list,
        _In_ PCWSTR name,
        _In_ bool capture,
        _Outptr_result_maybenull_ PUNKNOWN* port_unknown);

    NTSTATUS InstallTopology(
        _In_ PDEVICE_OBJECT device_object,
        _In_ PIRP irp,
        _In_ PRESOURCELIST resource_list,
        _In_ PCWSTR name,
        _In_ bool capture,
        _Outptr_result_maybenull_ PUNKNOWN* port_unknown);

    static JinkraVirtualCable cable_;
    static JinkraMasterClock master_clock_;
};
