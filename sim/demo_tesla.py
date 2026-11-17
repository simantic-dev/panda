"""openpilot's side of a Tesla Model 3, against one simulated panda running this repo's firmware.

Like sim/demo.py, but every batch panda returns from the car goes through opendbc's own Tesla CarInterface,
the CarState parser openpilot's card.py runs, and steering commands are built with opendbc's teslacan.
The car (sim/cars/car.py, bus 0) and the camera (sim/cars/camera.py, bus 2) replay tesla_model_3.json.

Usage: .venv/bin/python sim/demo_tesla.py   (./demo tesla starts the simulator first)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_panda  # noqa: E402

Panda = sim_panda.install(5781)
from opendbc.car.can_definitions import CanData  # noqa: E402
from opendbc.car.structs import CarParams  # noqa: E402
from opendbc.car.tesla.interface import CarInterface  # noqa: E402
from opendbc.car.tesla.values import CAR  # noqa: E402

CAR_MODEL = CAR.TESLA_MODEL_3
CP = CarInterface.get_non_essential_params(CAR_MODEL)
CI = CarInterface(CP)
safety = CP.safetyConfigs[0]
SAFETY_NAME = {v: k for k, v in CarParams.SafetyModel.schema.enumerants.items()}

p = Panda(Panda.sim_serial_at(5781))  # waits for the simulated panda to boot and attach, like plugging it in
CS = None
next_print = 0.0


def recv():
  """One can_recv batch through opendbc's CarState parser, as card.py does. Returns the raw batch."""
  global CS, next_print
  msgs = p.can_recv()
  t = Panda.sim_time()
  CS = CI.update([(int(t * 1e9), [CanData(a, d, b) for a, d, b in msgs])])
  if t >= next_print:
    next_print = t + 1.0
    print(f"  {t:5.2f} s  CarState vEgo={CS.vEgo:.2f} steeringAngleDeg={CS.steeringAngleDeg:.1f} "
          f"cruiseState.enabled={CS.cruiseState.enabled} cruiseState.speed={CS.cruiseState.speed:.2f} "
          f"gasPressed={CS.gasPressed} brakePressed={CS.brakePressed} standstill={CS.standstill} "
          f"canValid={CS.canValid} | panda controls_allowed={p.health()['controls_allowed']}")
  return msgs


def engaged():
  return CS is not None and CS.cruiseState.enabled


def tick(seconds):
  """openpilot's 10 Hz loop: heartbeat (engaged as the car reports it), parse the car, wait.
  Runs to a simulated-time deadline: each USB request also costs simulated time."""
  end = Panda.sim_time() + seconds
  while Panda.sim_time() < end:
    p.send_heartbeat(engaged=engaged())
    recv()
    Panda.sim_sleep(0.1)


def steer(angle):
  """DAS_steeringControl with ANGLE_CONTROL, built by opendbc's teslacan; panda echoes it or returns it rejected."""
  addr, dat, bus = CI.CC.tesla_can.create_steering_control(angle, True)
  p.can_send(addr, dat, bus)
  verdict = None
  while verdict is None:
    assert Panda.sim_time() < 20, "panda never answered"
    p.send_heartbeat(engaged=engaged())
    for a, _, b in recv():
      if a == addr and (b & 0xC0) == 0xC0:
        verdict = True   # rejected by the safety hook
      elif a == addr and (b & 0xC0) == 0x80:
        verdict = False  # tx echo: it went out on the bus
    Panda.sim_sleep(0.01)
  print(f"  {Panda.sim_time():5.2f} s  openpilot DAS_steeringControl angle {angle:+.1f} deg -> {'BLOCKED by panda' if verdict else 'sent to car'}")
  return verdict


print(f"panda {p.get_usb_serial()[:8]}  firmware {p.get_version()}")
p.set_safety_mode(safety.safetyModel.raw, safety.safetyParam)
print(f"safety mode {SAFETY_NAME[p.health()['safety_mode']]} param 0x{safety.safetyParam:x}, as openpilot sets it for {CAR_MODEL}\n")

tick(1.5)
assert CS.canValid and not CS.cruiseState.enabled, CS
print(f"\ncruise off: controls_allowed={p.health()['controls_allowed']}")
assert steer(0.1), "panda let a steering command through with cruise off"

while not p.health()["controls_allowed"]:  # the car engages cruise; panda sees DI_state on the bus
  assert Panda.sim_time() < 10, f"panda never allowed controls: {p.health()}"
  tick(0.1)
print(f"\ncruise on:  controls_allowed={p.health()['controls_allowed']}  (panda saw DI_state ENABLED by {Panda.sim_time():.2f} s)")
assert CS.cruiseState.enabled, CS
assert not steer(0.1), "panda blocked a small in-limit steering command while engaged"
assert steer(10.0), "panda let a 10 deg step at 90 km/h through"
tick(1.0)

h = p.health()
print(f"\nhealth: safety_tx_blocked {h['safety_tx_blocked']}  safety_rx_invalid {h['safety_rx_invalid']}  faults {h['faults']}")
assert h["safety_rx_invalid"] == 0 and h["controls_allowed"], h
