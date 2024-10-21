from smbus2 import SMBus
import time

class Bmp280(object):
    """
        Class to interact with BMP280 sensor chip
    """

    BMP280_CHIP_ID = 0x58

    DEFAULT_ADDRESS = 0x77

    MODE_SLEEP = 0x00
    MODE_FORCED = 0x02
    MODE_NORMAL = 0x03

    REG_CHIP_ID = 0xd0
    REG_RESET = 0xe0
    REG_STATUS = 0xf3
    REG_CTRL_MEAS = 0xf4
    REG_CONFIG = 0xf5
    REG_PRESS_MSB = 0xf7
    REG_PRESS_LSB = 0xf8
    REG_PRESS_XLSB = 0xf9
    REG_TEMP_MSB = 0xfa
    REG_TEMP_LSB = 0xfb
    REG_TEMP_XLSB = 0xfc

    REG_CALIB_BASE = 0x88

    RESET_MAGIC = 0xb6

    BIT_UPDATING = (1 << 0)
    BIT_MEASURING = (1 << 3)

    def __init__(self, bus: SMBus, address: int = DEFAULT_ADDRESS):
        """
        :param bus: SMBus instance of the bus where the sensor is allocated
        :param address:  integer which is the sensor address on the bus
        """
        # i2c/spi bus instance
        self.bus = bus

        # address of the chip on the bus
        self.address = address

        # calibration data, used to do the proper computation to get temp and pressure
        self.calibration_data = [0] * 12

        # Set the default power mode, which is mode_sleep right after power-on-reset
        self.power_mode = self.MODE_FORCED

        # Oversampling values; higher values means higher precision, but also higher power usage and slower
        # sampling rate
        self.oversampling_temp = 1
        self.oversampling_press = 1

        # Pressure value obtained from the sensor
        self.temperature = 0.0

        # Temperature value obtained from the sensor
        self.pressure = 0.0

        # Timestamp of the last sensor measurement
        self.time = 0.0

        self._initialize_chip()

    def _initialize_chip(self):
        """
            Do a softreset of the chip, take calibration data and initialize it with default settings
        :return:
        """
        # Do soft reset of the chip
        self.bus.write_byte(self.address, self.REG_RESET, self.RESET_MAGIC)

        # Wait until bit 0 of status register turns to 0. When this happens, the
        # chip is ready
        updating = True
        while updating:
            time.sleep(0.001)
            status = self.bus.read_byte_data(self.address, self.REG_STATUS)
            updating = (status & self.BIT_UPDATING) > 0

        # Read and check the chip_id with proper product
        chip_id = self.bus.read_byte_data(self.address, self.REG_CHIP_ID)
        if chip_id != self.BMP280_CHIP_ID:
            raise ValueError("Chip ID 0x%02x does not match with BMP280 product" % (chip_id,))

        # Read the calibration data (26 bytes). Last two bytes are expected to be 0x00, so check them too
        calibration_data = self.bus.read_i2c_block_data(self.address, self.REG_CALIB_BASE, 26)
        if calibration_data[24] != 0x00:
            raise ValueError("Invalid calibration data, byte 24 is not 0x00")
        if calibration_data[25] != 0x00:
            raise ValueError("Invalid calibration data, byte 25 is not 0x00")

        # Calibration data is a set of short/unsigned short 16-bit values. We convert all of them to signed shorts
        # here, and later we reconverted 0th and 3rd words to unsigned short, as per specs
        for word in range(0, 12):
            lsb = word * 2
            msb = lsb + 1
            sign = 1 if calibration_data[msb] & 0x80 else 0
            self.calibration_data[word] = (((calibration_data[msb] & 0x7f) << 8) | calibration_data[lsb]) - (sign * 32768)

        for word in [0, 3]:
            if self.calibration_data[word] < 0:
                self.calibration_data[word] += 65536

    def _compensate_temp(self, adc_t: int, dig_t1: int, dig_t2: int, dig_t3) -> tuple:
        """
            Compensation formulae for temperature.
            See chapter 8.1 of the official datasheet
        :param adc_t:
        :param dig_t1:
        :param dig_t2:
        :param dig_t3:
        :return:
        """
        var1 = (((adc_t >> 3) - (dig_t1 << 1)) * dig_t2) >> 11
        var2 = (((adc_t >> 4) - dig_t1) * (((adc_t >> 4) - dig_t1) >> 12) * dig_t3) >> 14
        t_fine = var1 + var2

        temp = (t_fine * 5 + 128) >> 8

        return temp / 100, t_fine

    def _compensate_pressure(self, adc_p: int, t_fine: int, dig_p1: int, dig_p2: int, dig_p3: int, dig_p4: int, dig_p5: int,
                             dig_p6: int, dig_p7: int, dig_p8: int, dig_p9: int) -> float:
        """
            Compensation formulae for pressure
            See chapter 8.1 of the official datasheet
        :param adc_p:
        :param t_fine:
        :param dig_p1:
        :param dig_p2:
        :param dig_p3:
        :param dig_p4:
        :param dig_p5:
        :param dig_p6:
        :return:
        """

        var1 = (t_fine - 128000)
        var2 = var1 * var1 * dig_p6
        var2 += (var1 * dig_p5) << 17
        var2 += dig_p4 << 35

        var1 = ((var1 * var1 * dig_p3) >> 8) + ((var1 * dig_p2) << 12)
        var1 = (((1 << 47) + var1) * dig_p1) >> 33

        if var1 == 0:
            return 0

        p = 1048576 - adc_p
        p = (((p << 31) - var2) * 3125) // var1

        var1 = (dig_p9 * (p >> 13) * (p >> 13)) >> 25
        var2 = (dig_p8 * p) >> 19

        p = ((p + var1 + var2) >> 8) + (dig_p7 << 4)

        return p / 25600.0

    def set_mode(self, mode):
        """
            Set chip mode between MODE_FORCED and MODE_NORMAL.
            MODE_FORCED is a one-shot type mode: measurement is taken when @see do_measure() is called, then the chip goes
                automatically to SLEEP mode.
            MODE_NORMAL sets the chip to continuously take measurements on its own; @see do_measure() is still needed
                to collect fresh data from the chip whenever needed.
        :param mode:
        :return:
        """
        # Mode is already set as defined mode, do nothing
        if mode == self.power_mode:
            return

        if mode == self.MODE_FORCED:
            # When MODE_FORCED is wanted, we just exit the NORMAL mode and enter into SLEEP mode
            # later, when a measurement is requested, we call MODE_FORCED to wake up the sensor and do the measurement
            meas = (self.oversampling_temp << 5) | (self.oversampling_press << 2) | self.MODE_SLEEP
            self.bus.write_byte_data(self.address, self.REG_CTRL_MEAS, meas)
        elif mode == self.MODE_NORMAL:
            # Enter NORMAL mode, where the sensor reads the values in cyclically. Still you need to call
            # do_measure() to read the values from the sensor to the library, and then read the values with
            # getters
            meas = (self.oversampling_temp << 5) | (self.oversampling_press << 2) | self.MODE_NORMAL
            self.bus.write_byte_data(self.address, self.REG_CTRL_MEAS, meas)
        else:
            raise ValueError("invalid power mode selected")

        self.power_mode = mode

    def do_measure(self):
        """
            Triggers a measurement from the sensor chip and stores the data internally.
            Data can be later retrieved with @see get_temperature() and @see get_pressure()
        :return:
        """
        # If the chip is in sleep mode, do measure trigger the "forced" mode (one-shot sampling)
        if self.power_mode == self.MODE_FORCED:
            meas = (self.oversampling_temp << 5) | (self.oversampling_press << 2) | self.MODE_FORCED
            self.bus.write_byte_data(self.address, self.REG_CTRL_MEAS, meas)

            while True:
                meas = self.bus.read_byte_data(self.address, self.REG_CTRL_MEAS)
                if (meas & 0x3) == 0:
                    break
                time.sleep(0.001)

        # We have to wait for bit 3 on status register to turn 0; once then, result of measurement has
        # been transferred to data registers
        while True:
            status = self.bus.read_byte_data(self.address, self.REG_STATUS)
            if status & self.BIT_MEASURING == 0:
                break
            time.sleep(0.001)

        # Read the data registers of both raw pressure and raw temperature in a single burst, as suggested by specs
        data = self.bus.read_i2c_block_data(self.address, self.REG_PRESS_MSB, 6)

        # Calculate the raw pressure and raw temperature values
        raw_pressure = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        raw_temperature = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)

        self.temperature, t_fine = self._compensate_temp(raw_temperature, *self.calibration_data[0:3])
        self.pressure = self._compensate_pressure(raw_pressure, t_fine, *self.calibration_data[3:])
        self.time = time.time()

    def get_temperature(self):
        return self.temperature

    def get_pressure(self):
        return self.pressure

    def get_time(self):
        return self.time


