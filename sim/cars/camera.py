# The car's camera on panda's bus 2 (FDCAN3), where panda forwards the car's traffic in a car safety mode.
# It has to be on the bus to acknowledge frames; without it panda's bus 2 queue fills and panda stops
# taking frames from USB, as a real panda with the camera unplugged would. It also replays the camera's
# messages in <car>.json (e.g. Tesla's DAS_control/DAS_steeringControl, which panda's Tesla safety checks
# on bus 2), cycling the 16 packed frames per message. Scripted.CanNode contract.
import json
import os

CAR = os.environ.get("SIM_CAR", "toyota_prius")


class Node:
  def __init__(self, ctx):
    self.ctx = ctx
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "sim/cars"
    spec = json.load(open(os.path.join(here, f"{CAR}.json")))
    self.msgs = [(m["addr"], 1_000_000 // m["hz"], [bytes.fromhex(f) for f in m["off"]]) for m in spec["camera"]]
    self.next_us = [0] * len(self.msgs)
    if self.msgs:
      ctx.schedule_periodic(1000)

  def on_timer(self):
    now = self.ctx.now_us
    for i, (addr, period, frames) in enumerate(self.msgs):
      if now >= self.next_us[i]:
        self.ctx.send(addr, frames[(now // period) % len(frames)])
        self.next_us[i] = now + period

  def on_frame(self, frame):
    pass
