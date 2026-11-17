"""Packs a car's messages with opendbc (comma's DBCs and checksums) for the in-simulator car peer.

The peer runs inside the simulator's Python, which cannot import opendbc's numpy, so the frames are
packed here once. Usage: .venv/bin/python sim/cars/gen_frames.py toyota_prius
"""
import json
import os
import sys

from opendbc.can import CANPacker
from opendbc.car.toyota.values import CAR, DBC

# The messages panda's Toyota safety checks before it allows control, at the rates it checks them
# (opendbc/safety/modes/toyota.h TOYOTA_RX_CHECKS). "on" is the car with cruise engaged.
CARS = {
  "toyota_prius": (CAR.TOYOTA_PRIUS, [
    ("WHEEL_SPEEDS", 83, {}, {}),
    ("STEER_TORQUE_SENSOR", 50, {}, {}),
    ("PCM_CRUISE", 33, {"CRUISE_ACTIVE": 0}, {"CRUISE_ACTIVE": 1}),
    ("BRAKE_MODULE", 40, {}, {}),
  ]),
}

name = sys.argv[1]
car, messages = CARS[name]
packer = CANPacker(DBC[car]["pt"])
out = {"car": str(car), "dbc": DBC[car]["pt"], "messages": []}
for msg, hz, off, on in messages:
  addr, off_dat, _ = packer.make_can_msg(msg, 0, off)
  _, on_dat, _ = packer.make_can_msg(msg, 0, on)
  out["messages"].append({"name": msg, "addr": addr, "hz": hz, "off": off_dat.hex(), "on": on_dat.hex()})
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.json")
json.dump(out, open(path, "w"), indent=1)
print(f"{path}: {len(out['messages'])} messages for {car}")
