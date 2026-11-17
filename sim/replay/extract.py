"""Pre-extracts a window of comma's public Tesla Model 3 test drive into JSON for ./demo tesla-replay.

Downloads segment SEG's rlog the way opendbc's car tests do (comma API /v1/route/<route>/files, no login)
into ../tesla-route/rlog/, and cereal's schema pinned at OPENPILOT_SHA into ../tesla-route/cereal/
(neither is committed). Needs the zstd CLI. Run with the repo's 3.12 venv (pycapnp from opendbc).

Usage: .venv/bin/python sim/replay/extract.py   -> ../tesla-route/window.json
"""
import json
import os
import subprocess
import urllib.request

import capnp

ROUTE = "79d0f04c82980004/00000003--fb0b5d9cfc"  # TESLA_MODEL_3 in opendbc/car/tests/routes.py (HW4 2025)
SEG = 7                                            # the segment where openpilot engages (controlsAllowed False -> True)
BEFORE_S, AFTER_S = 6.0, 24.0                      # window around that engagement
OPENPILOT_SHA = "b3ab22efe1be5d6c0ad46503f0985b26f8b7a36f"  # openpilot master, 2026-11-17: openpilot/cereal/*.capnp
OPENDBC_SHA = "27fa1c5d8eed3238a0a78c52ff5abb6cdc807bd2"    # its opendbc_repo submodule: car.capnp
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tesla-route")


def fetch(url, path):
  if not os.path.exists(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(url) as r, open(path + ".tmp", "wb") as f:
      f.write(r.read())
    os.replace(path + ".tmp", path)
  return path


def load_schema():
  d = os.path.join(OUT, "cereal", OPENPILOT_SHA[:8])
  raw = "https://raw.githubusercontent.com/commaai"
  for f in ("log", "custom", "deprecated", "include/c++"):
    fetch(f"{raw}/openpilot/{OPENPILOT_SHA}/openpilot/cereal/{f}.capnp", os.path.join(d, f + ".capnp"))
  fetch(f"{raw}/opendbc/{OPENDBC_SHA}/opendbc/car/car.capnp", os.path.join(d, "car.capnp"))
  capnp.remove_import_hook()
  return capnp.load(os.path.join(d, "log.capnp"), imports=[d])


def rlog_path():
  path = os.path.join(OUT, "rlog", f"{SEG}.zst")
  if not os.path.exists(path):
    with urllib.request.urlopen(f"https://api.commadotai.com/v1/route/{ROUTE.replace('/', '%7C')}/files") as r:
      url = next(u for u in json.load(r)["logs"] if f"/{SEG}/rlog." in u)
    fetch(url, path)
  return path


def main():
  log = load_schema()
  raw = subprocess.run(["zstd", "-dc", rlog_path()], capture_output=True, check=True).stdout
  events = sorted(log.Event.read_multiple_bytes(raw), key=lambda e: e.logMonoTime)
  ps = [(e.logMonoTime, e.pandaStates[0]) for e in events if e.which() == "pandaStates"]
  engage = next(t for (t, s), (_, prev) in zip(ps[1:], ps) if s.controlsAllowed and not prev.controlsAllowed)
  t0, t1 = engage - int(BEFORE_S * 1e9), engage + int(AFTER_S * 1e9)
  us = lambda t: (t - t0) // 1000
  cp = next(e.carParams for e in events if e.which() == "carParams")
  init = next(e.initData for e in events if e.which() == "initData")
  # pandaStates faults: FaultType ordinals, which are the bit numbers of health()["faults"] (board/sys/sys.h)
  out = {"route": ROUTE, "segment": SEG, "openpilot_sha": OPENPILOT_SHA, "opendbc_sha": OPENDBC_SHA,
         "openpilot_version": init.version, "openpilot_commit": init.gitCommit,
         "car": cp.carFingerprint, "safety_model": cp.safetyConfigs[0].safetyModel.raw,
         "safety_param": cp.safetyConfigs[0].safetyParam,
         "fault_types": dict(log.PandaState.FaultType.schema.enumerants),
         "engage_us": us(engage), "bus0": [], "bus2": [], "sendcan": [], "engaged": [], "panda": []}
  prev_can = None
  for e in events:
    w, t = e.which(), e.logMonoTime
    if w == "can":
      # A can event is one batch pandad read (~100 Hz); spread its frames over the gap since the last batch
      # so the car's traffic is not replayed as one burst. src >= 128 are panda's tx echoes, never car traffic.
      frames = [m for m in e.can if m.src in (0, 2)]
      gap = min(t - prev_can, 20_000_000) if prev_can else 0
      prev_can = t
      if t0 <= t < t1:
        for i, m in enumerate(frames):
          ti = t - gap * (len(frames) - 1 - i) // len(frames)
          out[f"bus{m.src}"].append([max(0, us(ti)), m.address, bytes(m.dat).hex()])
    elif not t0 <= t < t1:
      continue
    elif w == "sendcan":
      if len(e.sendcan):
        out["sendcan"].append([us(t), [[m.src, m.address, bytes(m.dat).hex()] for m in e.sendcan]])
    elif w == "selfdriveState":
      out["engaged"].append([us(t), e.selfdriveState.enabled])
    elif w == "pandaStates":
      s = e.pandaStates[0]
      out["panda"].append([us(t), s.controlsAllowed, s.safetyTxBlocked, s.safetyRxInvalid, sum(1 << f.raw for f in s.faults),
                           str(s.safetyModel), s.safetyParam])
  path = os.path.join(OUT, "window.json")
  json.dump(out, open(path, "w"))
  print(f"{path}: {len(out['bus0'])} bus 0 + {len(out['bus2'])} bus 2 frames, {len(out['sendcan'])} sendcan batches, "
        f"{len(out['panda'])} pandaStates over {(t1 - t0) / 1e9:.0f} s; engaged at {out['engage_us'] / 1e6:.2f} s")


if __name__ == "__main__":
  main()
