# The camera's side of the recorded drive: sim/cars/replay.py for bus 2.
import os

BUS = 2
exec(open(os.path.join("sim", "cars", "replay.py")).read())
