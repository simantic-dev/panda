# The car on the panda's bus 0 (FDCAN1): sends the messages in <car>.json (packed by opendbc, see
# gen_frames.py) at the car's own rates in virtual time, cycling each message's
# 16 packed frames so counters and checksums advance, engages cruise at ENGAGE_AT_S, and logs every
# frame that reaches it, i.e. what panda let through from openpilot. Scripted.CanNode contract.
import json
import os

CAR = os.environ.get("SIM_CAR", "toyota_prius")
ENGAGE_AT_S = float(os.environ.get("SIM_ENGAGE_AT_S", "3.0"))
TICK_US = 1000


class Node:
  def __init__(self, ctx):
    self.ctx = ctx
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "sim/cars"
    spec = json.load(open(os.path.join(here, f"{CAR}.json")))
    self.msgs = [(m["addr"], 1_000_000 // m["hz"], [bytes.fromhex(f) for f in m["off"]], [bytes.fromhex(f) for f in m["on"]])
                 for m in spec["messages"]]
    # panda forwards the camera's own frames here (bus 2 -> 0); those are not logged, openpilot's are
    self.camera_frames = {(m["addr"], f) for m in spec["camera"] for f in m["off"]}
    self.next_us = [0] * len(self.msgs)
    self.n = [0] * len(self.msgs)
    self.engaged = False
    ctx.info(f"car {spec['car']} ({spec['dbc']}), cruise engages at {ENGAGE_AT_S:.1f} s")
    ctx.schedule_periodic(TICK_US)

  def on_timer(self):
    now = self.ctx.now_us
    if not self.engaged and now >= ENGAGE_AT_S * 1e6:
      self.engaged = True
      self.ctx.info(f"cruise ENGAGED at {now / 1e6:.3f} s")
    for i, (addr, period, off, on) in enumerate(self.msgs):
      if now >= self.next_us[i]:
        frames = on if self.engaged else off
        self.ctx.send(addr, frames[self.n[i] % len(frames)])
        self.n[i] += 1
        self.next_us[i] = now + period

  def on_frame(self, frame):
    if (frame["id"], bytes(frame["data"]).hex()) in self.camera_frames:
      return
    self.ctx.info(f"on car bus: id=0x{frame['id']:03x} data={bytes(frame['data']).hex()} at {self.ctx.now_us / 1e6:.3f} s")
