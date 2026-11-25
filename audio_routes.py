"""Jinkra 自带的 Windows 录音和混音端点。"""

import re

MIC_ENDPOINT = "Jinkra Virtual Mic"
MIX_ENDPOINT = "Jinkra Mix Input"
ADAPTER = "Jinkra Virtual Audio"


def is_jinkra_endpoint(description: str) -> bool:
    parts = re.split(r"[()（）]", description.casefold())
    labels = {re.sub(r"^\d+\s*-\s*", "", part.strip()) for part in parts}
    return bool(labels & {name.casefold() for name in (MIC_ENDPOINT, MIX_ENDPOINT, ADAPTER)})


def unique_endpoint(devices: list):
    matches = [device for device in devices if is_jinkra_endpoint(device.description())]
    return matches[0] if len(matches) == 1 else None
