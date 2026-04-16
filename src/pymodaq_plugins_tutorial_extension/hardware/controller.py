import time
import numpy as np
from dataclasses import dataclass


class MockActuator:

    def __init__(self, current=0):
        self._target_value = current
        self._current_value = current
    
    def move_at(self, value):
        self._target_value = value
        self._current_value = value

    def get_value(self):
        return self._current_value


class MockShutter(MockActuator):

    pass


@dataclass
class MockSpectrograph:

    integration_time: float = 50
    n_pixels: int = 1024
    readout_noise: int = 4
    dark_level: float = 150
    light_level: float = 500
    pe_per_lsb: float = 18.3
    adc_bits: int = 16
    wl_from: float = 300
    wl_to: float = 900
    absorption: float = 0.3
    shutter_names = ['dark', 'excitation']

    def __post_init__(self):
        self.calculate_base_data()
        self.with_sample = True
        self.shutter = { name: MockShutter(1200) for name in self.shutter_names }

    def calculate_base_data(self):
        n_pix = self.n_pixels
        self.wavelengths = np.linspace(self.wl_from, self.wl_to, n_pix)
        self.pixels = np.linspace(0, n_pix - 1, n_pix)
        self.spectrum = np.exp(-((self.pixels - n_pix / 2) / (n_pix / 3))**4)
        self.absorption = \
            self.absorption \
            * np.exp(-((self.pixels - n_pix / 4) / (n_pix / 8))**2)

    def simulate_spectrum(self, shutter_open: bool, sample: bool):
        data = np.random.normal(loc=self.dark_level * self.integration_time,
                                scale=self.readout_noise, size=self.n_pixels)
        if shutter_open:
            light = self.spectrum * self.light_level * self.integration_time \
                * self.pe_per_lsb
            if sample:
                light *= np.pow(10, -self.absorption)
            data += np.random.poisson(light) / self.pe_per_lsb
        max_adc = (1 << self.adc_bits) - 1
        data = np.where(data < max_adc, np.floor(data), max_adc)

        return data, time.time()

    def grab_spectrum(self):
        time.sleep(max(self.integration_time * 1e-6, 0.001))
        #return self.simulate_spectrum(self.get_shutter_value('dark') > 1000,
        #                              self.with_sample)
        return self.simulate_spectrum(self.get_shutter_value('dark') > 0,
                                      self.with_sample)

    def get_shutter_value(self, axis):
        return self.shutter[axis].get_value()

    def set_shutter_value(self, axis, value):
        return self.shutter[axis].move_at(value)


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    spectrograph = MockSpectrograph()

    plt.plot(spectrograph.wavelengths, spectrograph.spectrum)
    plt.plot(spectrograph.wavelengths, spectrograph.absorption)
    plt.legend(['light spectrum', 'absorption'])
    plt.show()

    dark, time_stamp = \
        spectrograph.simulate_spectrum(shutter_open=False, sample=False)
    plt.plot(dark)
    plt.title('dark')
    plt.show()

    data, time_stamp = \
        spectrograph.simulate_spectrum(shutter_open=True, sample=False)
    plt.plot(data)
    reference = data - dark
    plt.plot(reference)
    plt.legend(['raw', 'dark subtracted'])
    plt.show()

    data, time_stamp = \
        spectrograph.simulate_spectrum(shutter_open=True, sample=True)
    plt.plot(data)
    signal = data - dark
    plt.plot(data - dark)
    plt.legend(['raw through sample', 'dark subtracted'])
    plt.show()

    plt.plot(-np.log10(signal / reference))
    plt.title('absorption')
    plt.show()
