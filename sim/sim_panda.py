"""comma's panda Python library, unmodified, against a simulated panda.

`install(*ports)` gives the library a USB handle per `sim --usb-raw <machine>.<controller>:<port>`
(JSON lines) in place of libusb. Nothing in panda/ is edited: `Panda.usb_connect`, `Panda.usb_list`,
`Panda.spi_connect` and `PandaDFU.list` are replaced from here, and the handle is wrapped in the
library's own `PandaUsbHandle`, which only needs the five libusb calls below.

    import sim_panda
    Panda = sim_panda.install(5781, 5782)
    dut, rig = (Panda(s) for s in Panda.list())
"""
import json
import os
import socket
import sys
import threading
import time

# The simulator applies a host request at its next 1 ms slice and may run slower than real time,
# so a libusb timeout given in wall-clock milliseconds is stretched: at least 5 s, else 200x.
def _wall_ms(timeout_ms):
    return max(5000, 200 * (timeout_ms or 15000))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # this panda checkout (pip install -e .)

import usb1  # the library's own dependency; only its exception types are used here



class Bridge:
    """One connection to the simulator's raw USB host bridge, kept across panda resets."""

    def __init__(self, port, timeout=120):
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        self.buf = b""
        self.lock = threading.RLock()  # libusb handles are thread safe; one request at a time here
        self.next_id = 0
        self.detached = False  # a detach was seen and no attach since
        self.configured = False

    def _event(self, reply):
        if reply.get("event") == "detach":
            self.detached, self.configured = True, False
        elif reply.get("event") == "attach":
            self.detached, self.configured = False, False

    def _readline(self, deadline):
        while b"\n" not in self.buf:
            self.sock.settimeout(max(0.05, deadline - time.monotonic()))
            try:
                chunk = self.sock.recv(65536)
            except (TimeoutError, socket.timeout):
                raise usb1.USBErrorTimeout()
            if not chunk:
                raise usb1.USBErrorNoDevice()
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def call(self, timeout_ms, **request):
        with self.lock:
            return self._call(_wall_ms(timeout_ms), **request)

    def _call(self, timeout_ms, **request):
        self.next_id += 1
        request["id"] = self.next_id
        self.sock.sendall((json.dumps(request) + "\n").encode())
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            reply = self._readline(deadline)
            if "event" in reply:
                self._event(reply)
                if self.detached:
                    raise usb1.USBErrorNoDevice()
            elif reply.get("id") == self.next_id:
                if "error" in reply:
                    raise usb1.USBErrorIO(reply["error"])
                return reply

    def wait_attached(self, timeout_s):
        with self.lock:
            return self._wait_attached(timeout_s)

    def _wait_attached(self, timeout_s):
        deadline = time.monotonic() + timeout_s
        while self.detached:
            try:
                self._event(self._readline(deadline))
            except usb1.USBErrorTimeout:
                return False
        return True

    def setup(self, request_type, request, value, index, length=0, data=b"", timeout_ms=15000):
        reply = self.call(timeout_ms, op="setup", bmRequestType=request_type, bRequest=request,
                          wValue=int(value) & 0xFFFF, wIndex=int(index) & 0xFFFF, wLength=length, data=bytes(data).hex())
        if reply.get("stall"):
            raise usb1.USBErrorPipe()
        return bytes.fromhex(reply["data"])

    def enumerate(self):
        """What a host does before a driver gets the device; returns the serial string."""
        with self.lock:
            return self._enumerate()

    def _enumerate(self):
        dev = self.setup(0x80, 6, 0x0100, 0, 18)
        self.setup(0x00, 5, 5, 0)
        head = self.setup(0x80, 6, 0x0200, 0, 9)
        config = self.setup(0x80, 6, 0x0200, 0, int.from_bytes(head[2:4], "little"))
        self.setup(0x00, 9, config[5], 0)
        self.configured = True
        self.vid, self.pid = int.from_bytes(dev[8:10], "little"), int.from_bytes(dev[10:12], "little")
        serial = self.setup(0x80, 6, 0x0300 | dev[16], 0x0409, 255)
        return serial[2:serial[0]].decode("utf-16-le")


class LibusbLikeHandle:
    """The part of a libusb1 device handle that panda's PandaUsbHandle uses."""

    def __init__(self, bridge):
        self.bridge = bridge

    def close(self):
        pass  # the simulator connection outlives a panda reset

    def controlWrite(self, request_type, request, value, index, data, timeout=0):
        self.bridge.setup(request_type & 0x7F, request, value, index, len(data), data, timeout or 15000)
        return len(data)

    def controlRead(self, request_type, request, value, index, length, timeout=0):
        return self.bridge.setup(request_type | 0x80, request, value, index, length, timeout_ms=timeout or 15000)

    def bulkWrite(self, endpoint, data, timeout=0):
        self.bridge.call(timeout or 15000, op="out", ep=endpoint, data=bytes(data).hex())
        return len(data)

    def bulkRead(self, endpoint, length, timeout=0):
        deadline = time.monotonic() + _wall_ms(timeout) / 1000
        out = bytearray()
        while len(out) < length:
            reply = self.bridge.call(timeout or 15000, op="in", ep=0x80 | endpoint)
            if reply.get("stall"):
                raise usb1.USBErrorPipe()
            if "data" not in reply:  # NAK: the host controller retries
                if time.monotonic() > deadline:
                    raise usb1.USBErrorTimeout()
                continue
            packet = bytes.fromhex(reply["data"])
            out += packet
            if len(packet) < 64:  # a short packet ends the transfer
                break
        return bytes(out)


class _NoContext:
    def close(self):
        pass


def install(*ports, hidden=()):
    """Points the panda library at the simulator (one --usb-raw port per simulated panda) and returns its
    Panda class. `Panda()` takes the first; `Panda(serial)` picks one, as with real hardware. Ports in
    `hidden` are left out of `Panda.list()` (a rig's panda that the host does not see) but open by serial."""
    from panda import Panda, PandaDFU
    from panda.python.usb import PandaUsbHandle

    bridges = [Bridge(port) for port in ports]
    serials = {}  # serial -> bridge; a serial is fixed per chip, so learn each once

    def serial_of(bridge, wait_s):
        if not bridge.wait_attached(wait_s):
            return None
        s = bridge.enumerate()
        serials[s] = bridge
        return s

    def usb_connect(cls, serial, claim=True, no_error=False):
        for bridge in ([serials[serial]] if serial in serials else bridges):
            try:
                this_serial = serial_of(bridge, 2)
            except usb1.USBError:
                continue
            if this_serial is None or (serial is not None and serial != this_serial):
                continue
            return _NoContext(), PandaUsbHandle(LibusbLikeHandle(bridge)), this_serial, (bridge.pid & 0xF0) == 0xE0
        return _NoContext(), None, None, None

    def serial_at(port, wait_s=180):
        return serial_of(bridges[ports.index(port)], wait_s)

    def usb_list(cls):
        out = []
        for port, bridge in zip(ports, bridges):
            if port in hidden:
                continue
            try:
                s = serial_of(bridge, 0.1)
            except usb1.USBError:
                s = None
            if s:
                out.append(s)
        return out

    Panda.usb_connect = classmethod(usb_connect)
    Panda.usb_list = classmethod(usb_list)
    Panda.spi_connect = classmethod(lambda cls, serial, ignore_version=False: (None, None, None, None))
    PandaDFU.list = staticmethod(lambda: [])
    Panda.sim_serial_at = staticmethod(serial_at)
    # Host sleeps in the simulation's time (sim --usb-raw `wait` op), as a real host shares real time with a real panda.
    Panda.sim_sleep = staticmethod(lambda seconds: bridges[0].call(1000 * seconds, op="wait", us=int(seconds * 1e6)))
    Panda.sim_time = staticmethod(lambda: bridges[0].call(1000, op="time")["t_us"] / 1e6)
    return Panda
