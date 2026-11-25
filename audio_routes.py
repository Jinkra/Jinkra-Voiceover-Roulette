"""Jinkra 可以送声的虚拟麦克风线路：自带驱动，或 VB-Audio 的 VB-CABLE。"""

import re
from dataclasses import dataclass

MIC_ENDPOINT = "Jinkra Virtual Mic"
MIX_ENDPOINT = "Jinkra Mix Input"
ADAPTER = "Jinkra Virtual Audio"


def _labels(description: str) -> set:
    parts = re.split(r"[()（）]", (description or "").casefold())
    return {re.sub(r"^\d+\s*-\s*", "", part.strip()) for part in parts}


@dataclass(frozen=True)
class Route:
    render: str        # Jinkra 写入混音的播放端
    capture: str       # 游戏和语音软件里要选的录音端
    qualifier: str = ""  # 端点名太短时，Windows 描述里还须带上的驱动名

    def _has(self, description, name):
        labels = _labels(description)
        return name.casefold() in labels and (not self.qualifier or self.qualifier.casefold() in labels)

    def render_matches(self, description: str) -> bool:
        return self._has(description, self.render)

    def capture_matches(self, description: str) -> bool:
        return self._has(description, self.capture)


JINKRA = Route(MIX_ENDPOINT, MIC_ENDPOINT)
VB_CABLE = Route("CABLE Input", "CABLE Output", "VB-Audio Virtual Cable")
ROUTES = (JINKRA, VB_CABLE)


def is_jinkra_endpoint(description: str) -> bool:
    return bool(_labels(description) & {n.casefold() for n in (MIC_ENDPOINT, MIX_ENDPOINT, ADAPTER)})


def route_of(description: str):
    """播放端所属的送声线路，不是线路播放端时返回 None。"""
    return next((route for route in ROUTES if route.render_matches(description)), None)


def unique_endpoint(devices: list, route=JINKRA, capture=True):
    match = route.capture_matches if capture else route.render_matches
    matches = [device for device in devices if match(device.description())]
    return matches[0] if len(matches) == 1 else None
