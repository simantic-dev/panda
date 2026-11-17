#!/usr/bin/env python3
"""Writes data.js for the panda demo video from the recorded run (pyrite docs/video: every number on screen
comes from the run's output, never typed into a scene).

  collect.py <runs/demo.txt> [data.js] [sim version]

runs/demo.txt is ./demo's stdout (record.sh). Asserts what the video claims; a failed assert means
re-record or change the video, not this script.
"""
import json, pathlib, re, sys

txt = pathlib.Path(sys.argv[1]).read_text()
out = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(__file__).with_name("data.js")

fw = re.search(r"^panda (\w+)\s+firmware (\S+)", txt, re.M)
mode = re.search(r"^safety mode (\w+) param (0x[0-9a-f]+), as openpilot sets it for (\w+)", txt, re.M)
off = re.search(r"^cruise off: controls_allowed=(\w+)", txt, re.M)
on = re.search(r"^cruise on:\s+controls_allowed=(\w+)\s+\(panda saw PCM_CRUISE engage at ([\d.]+) s\)", txt, re.M)
steers = [{"t": float(m[1]), "torque": int(m[2]), "blocked": m[3] == "BLOCKED by panda"}
          for m in re.finditer(r"^\s+([\d.]+) s\s+openpilot STEERING_LKA torque (\d+)\s+-> (BLOCKED by panda|sent to car)", txt, re.M)]
health = {k: int(v) for k, v in re.findall(r"(safety_tx_blocked|safety_rx_invalid|faults) (\d+)", txt)}
car_engage = float(re.search(r"^\s+cruise ENGAGED at ([\d.]+) s", txt, re.M)[1])
bus = [{"id": int(m[1], 16), "data": m[2], "t": float(m[3])}
       for m in re.finditer(r"^\s+on car bus: id=0x([0-9a-f]+) data=([0-9a-f]+) at ([\d.]+) s", txt, re.M)]

# What the video says, checked against the run.
assert fw and mode and off and on, "demo output incomplete"
assert off[1] == "False" and on[1] == "True"
assert [(s["torque"], s["blocked"]) for s in steers] == [(10, True), (10, False), (1600, True)], steers
assert steers[0]["t"] < car_engage <= float(on[2]) < steers[1]["t"], "block before engage, allowed after"
assert health == {"safety_tx_blocked": 2, "safety_rx_invalid": 0, "faults": 0}, health
assert len(bus) == 1 and bus[0]["id"] == 0x2E4, f"only STEERING_LKA reached the car: {bus}"
lka = bytes.fromhex(bus[0]["data"])
torque = int.from_bytes(lka[1:3], "big", signed=True)   # STEER_TORQUE_CMD, bytes 1-2 in comma's Toyota DBC
assert lka[0] & 1 and torque == 10, f"decoded {lka.hex()}"
assert steers[1]["t"] - 0.1 < bus[0]["t"] < steers[1]["t"], "the frame on the bus is the sent command"

DATA = {
    "sim": sys.argv[3] if len(sys.argv) > 3 else None,
    "serial": fw[1], "firmware": fw[2], "safety": mode[1], "param": mode[2], "car": mode[3],
    "steers": steers, "panda_engage": float(on[2]), "car_engage": car_engage,
    "bus": {**bus[0], "torque": torque}, "health": health,
}
out.write_text("// Written by collect.py from runs/demo.txt. Do not edit by hand.\nwindow.DATA = "
               + json.dumps(DATA, indent=1) + ";\n")
print(out, f"{len(steers)} steering commands, {len(bus)} frame on the car bus")
