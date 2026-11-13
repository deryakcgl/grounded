"""Link to the desk LED: send commands, read its messages.

Device counterpart: firmware/lib/grounded_led/led_protocol.h (change both together).

Two links with the same interface:
  SimLed     the virtual LED (firmware/test_native/led_sim): the firmware's own LedDevice code,
             run on the Mac and spoken to over a pipe. Used while there is no hardware.
  SerialLed  the real board over USB serial (needs: pip install pyserial).
"""
import queue
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "firmware/test_native"

RHYTHMS = ["Box 4-4-4-4", "4-7-8", "Relax 4-0-6-0"]   # same order as breath_pacer.cpp
CYCLE_S = [16, 19, 10]                                 # seconds per cycle of each rhythm


# --- Messages from the LED ---

@dataclass
class State:
    guiding: bool
    rhythm: int = None
    cycles: int = None


@dataclass
class Done:
    rhythm: int
    cycles_done: int


@dataclass
class Button:
    rhythm: int


@dataclass
class Rejected:
    message: str


def parse(line):
    """One line from the LED -> message object. Debug ('#') and malformed lines: None."""
    parts = line.strip().split(",")
    try:
        if parts == ["S", "IDLE"]:
            return State(False)
        if parts[0] == "S" and parts[1] == "GUIDE" and len(parts) == 4:
            return State(True, int(parts[2]), int(parts[3]))
        if parts[0] == "D" and len(parts) == 3:
            return Done(int(parts[1]), int(parts[2]))
        if parts[0] == "P" and len(parts) == 2:
            return Button(int(parts[1]))
        if parts[0] == "!":
            return Rejected(",".join(parts[1:]))
    except (ValueError, IndexError):
        pass
    return None


# --- Commands to the LED ---

def guide(rhythm, cycles):
    return f"G,{rhythm},{cycles}"


STOP, STATUS = "X", "?"


# --- Links ---

class _LineLink:
    """Common part: a background thread reads lines into a queue, so poll() never blocks."""

    def _start_reader(self, readline):
        self._lines = queue.Queue()

        def run():
            while line := readline():
                self._lines.put(line)
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        """All messages received since the last call (debug lines dropped)."""
        out = []
        while not self._lines.empty():
            msg = parse(self._lines.get())
            if msg is not None:
                out.append(msg)
        return out


class SimLed(_LineLink):
    def __init__(self, speed=1.0):
        subprocess.run(["make", "-s", "-C", str(NATIVE), "led_sim"], check=True)
        self.proc = subprocess.Popen([str(NATIVE / "led_sim"), "--speed", str(speed)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                     bufsize=1)          # line-buffered
        self._start_reader(self.proc.stdout.readline)

    def send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def close(self):
        self.proc.stdin.close()                          # led_sim exits when its input closes
        self.proc.wait(timeout=2)


class SerialLed(_LineLink):
    def __init__(self, port, baud=115200):
        import serial                                    # only needed for real hardware
        self.ser = serial.Serial(port, baud, timeout=0.5)
        self._start_reader(lambda: self.ser.readline().decode(errors="replace") or " ")

    def send(self, line):
        self.ser.write((line + "\n").encode())

    def close(self):
        self.ser.close()


def open_led(target, speed=1.0):
    """'sim' -> virtual LED; anything else is a serial port, e.g. /dev/tty.usbmodem1103.
    Asks for the state right away instead of relying on the LED's greeting: if the LED
    started before the host connected, that greeting was sent to nobody."""
    link = SimLed(speed) if target == "sim" else SerialLed(target)
    link.send(STATUS)
    return link
