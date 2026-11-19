> **[Simantic](https://simantic.com)** runs this firmware on simulated hardware, no board needed. Try it at [simantic.com](https://simantic.com).

# Welcome to panda

<!-- simantic-banner -->
> **Run this firmware with no hardware.** [Simantic](https://simantic.com) simulates the whole board, peripherals, sensors and buses included. Try it free at **[simantic.com](https://simantic.com)**, or run it locally: `curl -fsSL https://simantic.com/install | sh`


> **This fork:** panda's own firmware (bootstub + signed app, built from this repo) runs on a simulated
> STM32H723, on a simulated Toyota Prius's CAN bus, driven by comma's own panda library. No hardware.

```sh
./demo build   # once: Python 3.12 venv with this repo's dependencies, the firmware, the car's frames
./demo         # needs `sim` on PATH: curl -fsSL https://simantic.com/install | sh
```

![panda's Toyota safety on a simulated car](media/panda-demo.gif)

**[▶ Watch the 61 s explainer video](media/panda-demo-video.mp4)**

```mermaid
flowchart LR
  op["sim/demo.py: openpilot's side<br/>comma's panda library (python/)"]
  subgraph sim["Simantic simulator"]
    panda["STM32H723VG (cuatro)<br/>panda bootstub + signed app, unmodified"]
    car(["Toyota Prius, bus 0<br/>sim/cars/car.py: opendbc-packed frames<br/>at the car's rates"])
    cam(["camera, bus 2<br/>sim/cars/camera.py"])
  end
  op -- "USB: safety mode, heartbeat,<br/>STEERING_LKA, health" --> panda
  car -- "FDCAN1: WHEEL_SPEEDS, STEER_TORQUE_SENSOR,<br/>PCM_CRUISE, BRAKE_MODULE" --- panda
  panda -- "FDCAN3: forwarded traffic" --- cam
```

openpilot sets the safety mode it uses for a Prius (`toyota`, param from opendbc's `CarInterface`), and
panda's Toyota safety code decides what reaches the car: steering is blocked until panda sees cruise engage
on the car's bus, then allowed within limits, and an over-limit torque is blocked. Every car frame is packed
by opendbc from comma's Toyota DBC; the car replays them at the rates panda's safety checks. The host sleeps
in the simulator's time, so panda's timing checks see a real cadence.

Not modelled: the harness relay and ignition wiring, SPI to the comma device, and the car's response to
steering. The car is a replay, not a vehicle model. Simantic is a proprietary simulator, not open source.


panda speaks CAN and CAN FD, and it runs on the [STM32H725](https://www.st.com/resource/en/reference_manual/rm0468-stm32h723733-stm32h725735-and-stm32h730-value-line-advanced-armbased-32bit-mcus-stmicroelectronics.pdf).

## Directory structure

```
.
├── board           # Code that runs on the STM32
├── python          # Python userspace library for interfacing with the panda
├── tests           # Tests for panda
├── scripts         # Miscellaneous used for panda development and debugging
├── examples        # Example scripts for using a panda in a car
```

## Safety Model

panda is compiled with vehicle-specific safety logic provided by [opendbc](https://github.com/commaai/opendbc). See details about the car safety models, safety testing, and code rigor in that repository.

## Code Rigor

The panda firmware is written for its use in conjunction with [openpilot](https://github.com/commaai/openpilot). The panda firmware, through its safety model, provides and enforces the
[openpilot safety](https://github.com/commaai/openpilot/blob/master/docs/SAFETY.md). Due to its critical function, it's important that the application code rigor within the `board` folder is held to high standards.

These are the [CI regression tests](https://github.com/commaai/panda/actions) we have in place:
* A generic static code analysis is performed by [cppcheck](https://github.com/danmar/cppcheck/).
* In addition, [cppcheck](https://github.com/danmar/cppcheck/) has a specific addon to check for [MISRA C:2012](https://misra.org.uk/) violations. See [current coverage](https://github.com/commaai/panda/blob/master/tests/misra/coverage_table).
* Compiler options are strict: the flags `-Wall -Wextra -Wstrict-prototypes -Werror` are enforced.
* The [safety logic](https://github.com/commaai/panda/tree/master/opendbc/safety) is tested and verified by [unit tests](https://github.com/commaai/panda/tree/master/opendbc/safety/tests) for each supported car variant to ensure that the behavior remains unchanged.
* A hardware-in-the-loop test verifies panda's functionalities on all active panda variants, including:
  * additional safety model checks
  * compiling and flashing the bootstub and app code
  * receiving, sending, and forwarding CAN messages on all buses
  * CAN loopback and latency tests through SPI

The above tests are themselves tested by:
* a [mutation test](tests/misra/test_mutation.py) on the MISRA coverage
* a [mutation test]([tests/misra/test_mutation.py](https://github.com/commaai/opendbc/blob/master/opendbc/safety/tests/mutation.sh)) on the vehicle-specific safety logic

## Usage

```bash
git clone https://github.com/commaai/panda.git
cd panda

# setup your environment
./setup.sh

# build fw + run the tests
./test.sh
```

See [the Panda class](https://github.com/commaai/panda/blob/master/python/__init__.py) for how to interact with the panda.

For example, to receive CAN messages:
``` python
>>> from panda import Panda
>>> panda = Panda()
>>> panda.can_recv()
```
And to send one on bus 0:
``` python
>>> from opendbc.car.structs import CarParams
>>> panda.set_safety_mode(CarParams.SafetyModel.allOutput)
>>> panda.can_send(0x1aa, b'message', 0)
```
Note that you may have to setup [udev rules](https://github.com/commaai/panda/tree/master/drivers/linux) for Linux, such as
``` bash
sudo tee /etc/udev/rules.d/11-panda.rules <<EOF
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="df11", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="3801", ATTRS{idProduct}=="ddcc", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="3801", ATTRS{idProduct}=="ddee", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="bbaa", ATTRS{idProduct}=="ddcc", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="bbaa", ATTRS{idProduct}=="ddee", MODE="0666"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Licensing

panda software is released under the MIT license unless otherwise specified.
