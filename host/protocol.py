"""Parses the device -> host protocol.

Device counterpart: firmware/lib/grounded_dsp/protocol.h (change both together).
One event per line; times are milliseconds since the device started.
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
class LeadOff:
    t_ms: int
    bits: int          # ADS1292R LOFF_STAT[4:0]; 0 = all electrodes connected

    @property
    def connected(self):
        return self.bits == 0


@dataclass
class Hrv:
    t_ms: int
    rmssd_ms: float
    hr_bpm: float


def parse(line):
    """Turns one line into an event object. Malformed or unknown line: None.

    On a real link (serial port, Bluetooth) lines can arrive truncated or corrupted;
    we skip them instead of raising, so a single bad line doesn't stop the recording.
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
        if kind == "L" and len(nums) == 2:
            return LeadOff(*nums)
        if kind == "V" and len(nums) == 3:
            return Hrv(nums[0], nums[1] / 10.0, nums[2] / 10.0)
    except ValueError:
        pass
    return None
