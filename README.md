# bmp280
BMP280 is small python library and companion measurement example scripts. Reduces traffic on the i2c bus to the least amount required to get a fully working device and aims to be a completely cover the bmp280 features.
Only i2c bus is supported with this library.

# Dependencies
The only dependency is smbus2 library

# Basic usage

```python
from smbus2 import SMBus
from bmp280 import Bmp280
import time

bus_id = 1

bus = SMBus(bus_id)
bmp280 = Bmp280(bus)

bmp280.do_measure()

temperatue = bmp280.get_temperature()
pressure = bmp280.get_pressure()

print("Temperature: %.2f °C - Pressure: %.2f hPa" % (temperature, pressure))

```
