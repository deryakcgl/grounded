import queue
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATIVE = ROOT / "firmware/test_native"

RHYTHMS = ["Box 4-4-4-4", "4-7-8", "Relax 4-0-6-0"]
CYCLE_S = [16, 19, 10]


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


def guide(rhythm, cycles):
    return f"G,{rhythm},{cycles}"


STOP, STATUS = "X", "?"


class _LineLink:
    def _start_reader(self, readline):
        self._lines = queue.Queue()

        def run():
            while line := readline():
                self._lines.put(line)
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
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
                                     bufsize=1)
        self._start_reader(self.proc.stdout.readline)

    def send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=2)


class SerialLed(_LineLink):
    def __init__(self, port, baud=115200):
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.5)
        self._start_reader(lambda: self.ser.readline().decode(errors="replace") or " ")

    def send(self, line):
        self.ser.write((line + "\n").encode())

    def close(self):
        self.ser.close()


def open_led(target, speed=1.0):
    link = SimLed(speed) if target == "sim" else SerialLed(target)
    link.send(STATUS)
    return link
