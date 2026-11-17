"""openpilot's side of a recorded Tesla Model 3 drive, against one simulated panda; then the simulated panda's
safety decisions against the real panda's logged pandaStates.

The car (bus 0) and camera (bus 2) replay what the real panda received (sim/cars/replay.py). This host sends
openpilot's recorded sendcan at its logged times and, at each logged pandaStates time, the heartbeat with
openpilot's engaged state (selfdriveState.enabled) and a health read, as pandad does at 10 Hz.

Usage: .venv/bin/python sim/demo_tesla_replay.py   (./demo tesla-replay extracts the window and starts the simulator)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_panda  # noqa: E402

Panda = sim_panda.install(5781)
from opendbc.car.structs import CarParams  # noqa: E402

W = json.load(open(os.environ["SIM_REPLAY"]))
AT = float(os.environ.get("SIM_REPLAY_AT_S", "3"))
SAFETY_NAME = {v: k for k, v in CarParams.SafetyModel.schema.enumerants.items()}
FAULTS = {v: k for k, v in W["fault_types"].items()}  # cereal PandaState.FaultType; bit = ordinal


def names(mask):
  return ",".join(FAULTS.get(b, f"bit{b}") for b in range(32) if mask >> b & 1) or "none"


p = Panda(Panda.sim_serial_at(5781))
print(f"panda {p.get_usb_serial()[:8]}  firmware {p.get_version()}")
print(f"drive {W['route']} segment {W['segment']}, {W['car']}, openpilot {W['openpilot_version']} "
      f"({W['openpilot_commit'][:8]}); cereal schema at openpilot {W['openpilot_sha'][:8]}")
p.set_safety_mode(W["safety_model"], W["safety_param"])
h = p.health()
print(f"safety mode {SAFETY_NAME[h['safety_mode']]} param 0x{W['safety_param']:x}, from the log's carParams")
assert Panda.sim_time() < AT, f"host ready at {Panda.sim_time():.2f} s, after the replay started at {AT} s"
print(f"replaying {W['panda'][-1][0] / 1e6:.0f} s of the drive from {AT:.1f} s of simulated time\n")

events = sorted([(t, 0, b) for t, b in W["sendcan"]] + [(t, 1, s) for t, *s in W["panda"]], key=lambda e: e[:2])
eng = W["engaged"]
ie = 0
engaged = False
rows = []      # (t, real, sim, lag_us)
lags = []
for t_us, kind, ev in events:
  now = Panda.sim_time()
  if now < AT + t_us / 1e6:
    Panda.sim_sleep(AT + t_us / 1e6 - now)
  lags.append((Panda.sim_time() - AT) * 1e6 - t_us)
  if kind == 0:
    p.can_send_many([(a, bytes.fromhex(d), bus) for bus, a, d in ev])
    continue
  while ie < len(eng) and eng[ie][0] <= t_us:
    engaged = eng[ie][1]
    ie += 1
  p.send_heartbeat(engaged=engaged)
  h = p.health()
  rows.append((t_us, ev, h, (Panda.sim_time() - AT) * 1e6 - t_us))

sends = sum(1 for e in events if e[1] == 0)
lags.sort()
print(f"host: {sends} sendcan batches and {len(rows)} heartbeat+health reads over {W['panda'][-1][0] / 1e6:.1f} s of drive, "
      f"as logged; lateness vs log median {lags[len(lags) // 2] / 1e3:.1f} ms, p95 {lags[int(len(lags) * .95)] / 1e3:.1f} ms, "
      f"max {lags[-1] / 1e3:.1f} ms")

real0, sim0 = rows[0][1][1], rows[0][2]["safety_tx_blocked"]
real_on = next((t for t, r, _, _ in rows if r[0]), None)
sim_on = next((t for t, _, s, _ in rows if s["controls_allowed"]), None)
fmt = lambda t: "never" if t is None else f"{t / 1e6:.2f} s"
print(f"\nengage (controls_allowed False -> True): real {fmt(real_on)}  sim {fmt(sim_on)}  (window time; logged engage {W['engage_us'] / 1e6:.2f} s)")
print(f"safety_tx_blocked over the window: real +{rows[-1][1][1] - real0}  sim +{rows[-1][2]['safety_tx_blocked'] - sim0}")
print(f"safety model: real {rows[0][1][4]} param {rows[0][1][5]}; sim {SAFETY_NAME[rows[0][2]['safety_mode']]} param {W['safety_param']}")

mismatch = {}
for t, (allowed, blocked, rx_inv, faults, _, _), s, lag in rows:
  for field, real, sim in (("controls_allowed", allowed, bool(s["controls_allowed"])),
                           ("safety_tx_blocked delta", blocked - real0, s["safety_tx_blocked"] - sim0),
                           ("safety_rx_invalid", rx_inv, s["safety_rx_invalid"]),
                           ("faults", names(faults), names(s["faults"]))):
    if real != sim:
      mismatch.setdefault((field, real, sim), []).append(t)
print(f"\n{len(rows)} pandaStates samples compared; {'no mismatches' if not mismatch else 'mismatches (field: real vs sim, at window times):'}")
for (field, real, sim), ts in sorted(mismatch.items(), key=lambda kv: kv[1][0]):
  span = f"{ts[0] / 1e6:.2f} s" if len(ts) == 1 else f"{len(ts)} samples, {ts[0] / 1e6:.2f}..{ts[-1] / 1e6:.2f} s"
  print(f"  {field}: real {real} vs sim {sim}  ({span})")

sent = {}
for _, b in W["sendcan"]:
  for _, a, _ in b:
    sent[a] = sent.get(a, 0) + 1
c0, h = p.can_health(0), p.health()
print(f"\nopenpilot's frames sent to panda (bus 0): " + " ".join(f"0x{a:03x}:{n}" for a, n in sorted(sent.items()))
      + "; compare 'frames from panda' on bus 0 below")
print(f"panda bus 0: total_tx_cnt {c0['total_tx_cnt']} total_tx_lost_cnt {c0['total_tx_lost_cnt']} "
      f"total_fwd_cnt {c0['total_fwd_cnt']} bus_off_cnt {c0['bus_off_cnt']}; usb rx_buffer_overflow "
      f"{h['rx_buffer_overflow']} tx_buffer_overflow {h['tx_buffer_overflow']}")
