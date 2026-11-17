# The car's camera on panda's bus 2 (FDCAN3), where panda forwards the car's traffic in a car safety mode.
# It only has to be on the bus to acknowledge frames; without it panda's bus 2 queue fills and panda stops
# taking frames from USB, as a real panda with the camera unplugged would. Scripted.CanNode contract.
class Node:
  def __init__(self, ctx):
    self.ctx = ctx

  def on_frame(self, frame):
    pass
