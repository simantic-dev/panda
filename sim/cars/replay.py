# One node of a recorded drive (sim/replay/extract.py's window JSON at $SIM_REPLAY): sends the frames the real
# panda received on bus BUS at their logged offsets, starting at $SIM_REPLAY_AT_S of virtual time, and counts the
# frames that reach it from panda. The car on bus 0; replay_camera.py runs this for bus 2. Scripted.CanNode contract.
import json
import os

BUS = globals().get("BUS", 0)
AT_US = int(float(os.environ.get("SIM_REPLAY_AT_S", "3")) * 1e6)


class Node:
  def __init__(self, ctx):
    self.ctx = ctx
    self.frames = [(AT_US + t, a, bytes.fromhex(d)) for t, a, d in json.load(open(os.environ["SIM_REPLAY"]))[f"bus{BUS}"]]
    self.i, self.got = 0, {}
    ctx.info(f"bus {BUS}: replaying {len(self.frames)} recorded frames from {AT_US / 1e6:.1f} s")
    ctx.schedule_oneshot(self.frames[0][0])

  def on_timer(self):
    now = self.ctx.now_us
    while self.i < len(self.frames) and self.frames[self.i][0] <= now:
      self.ctx.send(self.frames[self.i][1], self.frames[self.i][2])
      self.i += 1
    if self.i < len(self.frames):
      self.ctx.schedule_oneshot(self.frames[self.i][0] - now)
    else:
      self.ctx.info(f"bus {BUS}: replay done at {now / 1e6:.3f} s; frames from panda by id: "
                    + " ".join(f"0x{a:03x}:{n}" for a, n in sorted(self.got.items())))

  def on_frame(self, frame):
    self.got[frame["id"]] = self.got.get(frame["id"], 0) + 1
