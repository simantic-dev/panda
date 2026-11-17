"""Packs a car's messages with opendbc (comma's DBCs, counters and checksums) for the in-simulator peers.

The peers run inside the simulator's Python, which cannot import opendbc's numpy, so the frames are
packed here once: 16 consecutive frames per message (opendbc's packer steps the counter and recomputes
the checksum), which the peer cycles through. Usage: .venv/bin/python sim/cars/gen_frames.py toyota_prius
"""
import json
import os
import sys

from opendbc.can import CANPacker
from opendbc.car.tesla.values import CAR as TESLA
from opendbc.car.toyota.values import CAR as TOYOTA
from opendbc.car.values import PLATFORMS

# Per car: (platform, DBC bus key, messages on panda's bus 0 from the car, messages on bus 2 from the camera).
# Each message is (name, hz, signals with cruise off, signals with cruise on). The bus 0 messages are the
# ones panda's safety mode checks before it allows control, at the rates it checks them (opendbc/safety/modes/).
CARS = {
  "toyota_prius": (TOYOTA.TOYOTA_PRIUS, "pt", [
    ("WHEEL_SPEEDS", 83, {}, {}),
    ("STEER_TORQUE_SENSOR", 50, {}, {}),
    ("PCM_CRUISE", 33, {"CRUISE_ACTIVE": 0}, {"CRUISE_ACTIVE": 1}),
    ("BRAKE_MODULE", 40, {}, {}),
  ], []),
  # tesla.h tesla_model3_y_rx_checks, plus what opendbc's Tesla CarState reads on bus 2. Steady 90 km/h.
  "tesla_model_3": (TESLA.TESLA_MODEL_3, "party", [
    ("DI_speed", 50, {"DI_vehicleSpeed": 90}, {}),
    ("ESP_B", 50, {"ESP_vehicleSpeed": 90, "ESP_wheelSpeedsQF": 1, "ESP_vehicleStandstillSts": 0}, {}),
    ("EPAS3S_sysStatus", 100, {"EPAS3S_internalSAS": 0, "EPAS3S_handsOnLevel": 0, "EPAS3S_eacStatus": 1}, {}),
    ("DI_systemStatus", 100, {"DI_accelPedalPos": 0, "DI_gear": 4}, {}),
    ("ESP_status", 50, {"ESP_driverBrakeApply": 1}, {}),
    ("DI_state", 10, {"DI_cruiseState": 1, "DI_autoparkState": 1, "DI_speedUnits": 1, "DI_digitalSpeed": 100},
     {"DI_cruiseState": 2}),
    ("UI_warning", 10, {"buckleStatus": 1, "anyDoorOpen": 0}, {}),
  ], [
    ("DAS_control", 25, {"DAS_accState": 0, "DAS_aebEvent": 0}, {}),
    ("DAS_steeringControl", 50, {"DAS_steeringControlType": 0}, {}),
    ("SCCM_steeringAngleSensor", 100, {}, {}),
    ("DAS_status", 2, {}, {}),
    ("DAS_settings", 2, {"DAS_autosteerEnabled": 0}, {}),
  ]),
}


def pack(packer, messages):
  out = []
  for msg, hz, off, on in messages:
    frames = {}
    for state, values in (("off", off), ("on", {**off, **on})):
      frames[state] = []
      for _ in range(16):
        addr, dat, _ = packer.make_can_msg(msg, 0, values)
        frames[state].append(dat.hex())
    out.append({"name": msg, "addr": addr, "hz": hz, **frames})
  return out


name = sys.argv[1]
car, bus, car_msgs, camera_msgs = CARS[name]
dbc = PLATFORMS[car].config.dbc_dict[bus]
packer = CANPacker(dbc)
out = {"car": str(car), "dbc": dbc, "messages": pack(packer, car_msgs), "camera": pack(packer, camera_msgs)}
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.json")
json.dump(out, open(path, "w"), indent=1)
print(f"{path}: {len(out['messages'])} car + {len(out['camera'])} camera messages for {car}")
