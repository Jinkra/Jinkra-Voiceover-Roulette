#include "adapter.h"

extern "C" DRIVER_INITIALIZE DriverEntry;

NTSTATUS JinkraAddDevice(
    _In_ PDRIVER_OBJECT driver_object,
    _In_ PDEVICE_OBJECT physical_device_object);

NTSTATUS JinkraStartDevice(
    _In_ PDEVICE_OBJECT device_object,
    _In_ PIRP irp,
    _In_ PRESOURCELIST resource_list);

namespace {
PDRIVER_UNLOAD g_portcls_unload = nullptr;
}

#pragma code_seg("PAGE")
extern "C"
void JinkraDriverUnload(PDRIVER_OBJECT driver_object) {
    PAGED_CODE();
    // PortCls tears the device down first; only then is it safe to release the ring the
    // stream DPCs were reading from. Without this the 64 KB of non-paged pool leaks on
    // every driver unload.
    if (g_portcls_unload != nullptr) {
        g_portcls_unload(driver_object);
    }
    JinkraAdapter::Shutdown();
}
#pragma code_seg()

#pragma code_seg("INIT")
extern "C"
NTSTATUS DriverEntry(
    PDRIVER_OBJECT driver_object,
    PUNICODE_STRING registry_path) {
    const NTSTATUS status = PcInitializeAdapterDriver(
        driver_object,
        registry_path,
        JinkraAddDevice);
    if (NT_SUCCESS(status)) {
        g_portcls_unload = driver_object->DriverUnload;
        driver_object->DriverUnload = JinkraDriverUnload;
    }
    return status;
}
#pragma code_seg()

#pragma code_seg("PAGE")
NTSTATUS JinkraAddDevice(
    PDRIVER_OBJECT driver_object,
    PDEVICE_OBJECT physical_device_object) {
    PAGED_CODE();
    return PcAddAdapterDevice(
        driver_object,
        physical_device_object,
        JinkraStartDevice,
        4,
        0);
}

NTSTATUS JinkraStartDevice(
    PDEVICE_OBJECT device_object,
    PIRP irp,
    PRESOURCELIST resource_list) {
    PAGED_CODE();

    auto* adapter = static_cast<JinkraAdapter*>(
        ExAllocatePool2(
            POOL_FLAG_NON_PAGED,
            sizeof(JinkraAdapter),
            JINKRA_POOLTAG));
    if (adapter == nullptr) {
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    new (adapter) JinkraAdapter();
    NTSTATUS status = adapter->Initialize(
        device_object,
        irp,
        resource_list);

    // The adapter object contains no per-device state after registration;
    // the shared cable has static lifetime. Release the temporary installer.
    adapter->~JinkraAdapter();
    ExFreePoolWithTag(adapter, JINKRA_POOLTAG);
    return status;
}
#pragma code_seg()
