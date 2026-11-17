"""openpilot's side of a car, against one simulated panda running this repo's firmware.

The car is sim/cars/car.py in the simulator (opendbc-packed frames at the car's rates); this script plays
openpilot: it sets the safety mode openpilot sets for that car, sends heartbeats and steering commands, and
reads panda's health. Whether a command reached the car is in the car's own log (./demo prints it).

Usage: .venv/bin/python sim/demo.py   (./demo starts the simulator first)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_panda  # noqa: E402

Panda = sim_panda.install(5781)
from opendbc.can import CANPacker  # noqa: E402
from opendbc.car.structs import CarParams  # noqa: E402
from opendbc.car.toyota.interface import CarInterface  # noqa: E402
from opendbc.car.toyota.values import CAR, DBC  # noqa: E402

CAR_MODEL = CAR.TOYOTA_PRIUS
safety = CarInterface.get_non_essential_params(CAR_MODEL).safetyConfigs[0]
packer = CANPacker(DBC[CAR_MODEL]["pt"])
SAFETY_NAME = {v: k for k, v in CarParams.SafetyModel.schema.enumerants.items()}

p = Panda(Panda.sim_serial_at(5781))  # waits for the simulated panda to boot and attach, like plugging it in


def tick(seconds, engaged):
  """openpilot's 10 Hz loop: heartbeat, drain the receive buffer, wait."""
  end = Panda.sim_time() + seconds  # by simulated time: each USB round trip also takes some
  while True:
    p.send_heartbeat(engaged=engaged)
    p.can_recv()
    Panda.sim_sleep(0.1)
    if Panda.sim_time() >= end - 0.05:
      break


def steer(torque, engaged):
  """panda answers every frame it gets: echoed back once it is on the bus, or returned as rejected."""
  addr, dat, bus = packer.make_can_msg("STEERING_LKA", 0, {"STEER_REQUEST": 1, "STEER_TORQUE_CMD": torque})
  p.can_send(addr, dat, bus)
  verdict = None
  while verdict is None:
    assert Panda.sim_time() < 15, "panda never answered"
    p.send_heartbeat(engaged=engaged)
    for a, _, b in p.can_recv():
      if a == addr and (b & 0xC0) == 0xC0:
        verdict = True   # rejected by the safety hook
      elif a == addr and (b & 0xC0) == 0x80:
        verdict = False  # tx echo: it went out on the bus
    Panda.sim_sleep(0.01)
  blocked = verdict
  print(f"  {Panda.sim_time():5.2f} s  openpilot STEERING_LKA torque {torque:<5} -> {'BLOCKED by panda' if blocked else 'sent to car'}")


print(f"panda {p.get_usb_serial()[:8]}  firmware {p.get_version()}")
p.set_safety_mode(safety.safetyModel.raw, safety.safetyParam)
print(f"safety mode {SAFETY_NAME[p.health()['safety_mode']]} param 0x{safety.safetyParam:x}, as openpilot sets it for {CAR_MODEL}")

tick(1.0 - Panda.sim_time(), False)  # virtual time: spread the story over ~5 s so each step reads on its own
print(f"\ncruise off: controls_allowed={p.health()['controls_allowed']}")
steer(10, False)

while not p.health()["controls_allowed"]:  # the car engages cruise; panda sees it on the bus
  assert Panda.sim_time() < 10, f"panda never allowed controls: {p.health()}"
  tick(0.1, True)
print(f"\ncruise on:  controls_allowed={p.health()['controls_allowed']}  (panda saw PCM_CRUISE engage at {Panda.sim_time():.2f} s)")
tick(1.0, True)
steer(10, True)
tick(1.0, True)
steer(1600, True)

h = p.health()
print(f"\nhealth: safety_tx_blocked {h['safety_tx_blocked']}  safety_rx_invalid {h['safety_rx_invalid']}  faults {h['faults']}")
