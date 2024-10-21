from smbus2 import SMBus
from bmp280 import Bmp280
import time

bus_id = 1

bus = SMBus(bus_id)
bmp280 = Bmp280(bus)

bmp280.set_mode(bmp280.MODE_NORMAL)

try:
    while True:
        bmp280.do_measure()
        print("Temperature: %.2f °C - Pressure: %.2f hPa" % (bmp280.get_temperature(), bmp280.get_pressure()))
        time.sleep(5)
except KeyboardInterrupt:
    pass

bmp280.set_mode(bmp280.MODE_FORCED)

print("done")

