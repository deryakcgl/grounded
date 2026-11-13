"""Cihaz -> host protokolunu cozer.

Cihaz karsiligi: firmware/lib/grounded_dsp/protocol.h (birlikte degistir).
Her satir bir olay; zamanlar cihaz acildigindan beri milisaniye.
"""
from dataclasses import dataclass


@dataclass
class Breath:
    t_ms: int
    interval_ms: int


@dataclass
class HoldStart:
    t_ms: int


@dataclass
class HoldEnd:
    t_ms: int
    duration_ms: int


@dataclass
class Hrv:
    t_ms: int
    rmssd_ms: float
    hr_bpm: float


def parse(line):
    """Bir satiri olay nesnesine cevirir. Bozuk ya da bilinmeyen satir: None.

    Gercek baglantida (seri port, Bluetooth) satirlar yarim ya da bozuk gelebilir;
    hata firlatmak yerine atlariz ki tek bir bozuk satir kaydi durdurmasin.
    """
    parts = line.strip().split(",")
    try:
        kind, nums = parts[0], [int(p) for p in parts[1:]]
        if kind == "B" and len(nums) == 2:
            return Breath(*nums)
        if kind == "H" and len(nums) == 1:
            return HoldStart(*nums)
        if kind == "E" and len(nums) == 2:
            return HoldEnd(*nums)
        if kind == "V" and len(nums) == 3:
            return Hrv(nums[0], nums[1] / 10.0, nums[2] / 10.0)
    except ValueError:
        pass
    return None
