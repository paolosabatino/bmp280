from smbus2 import SMBus
from bmp280 import Bmp280
import time

# This script is an example of taking measurements in NORMAL mode (ie: continuous measurements by the chip)

bus_id = 1

bus = SMBus(bus_id)
bmp280 = Bmp280(bus)

bmp280.t_standby = 0b101  # Set standby-time between measurements to 1000 ms (see chapter 3.6.3 of the datasheet)
bmp280.iir_filter = 8  # Set the chip to use 8-samples for iir filter

bmp280.set_mode(bmp280.MODE_NORMAL)  # Set the chip in normal mode

try:
    while True:
        bmp280.do_measure()
        print("Temperature: %.2f °C - Pressure: %.2f hPa" % (bmp280.get_temperature(), bmp280.get_pressure()))
        time.sleep(5)
except KeyboardInterrupt:
    pass

# Restore forced mode, not to keep the sensor taking measurements forever
bmp280.set_mode(bmp280.MODE_FORCED)

print("done")

