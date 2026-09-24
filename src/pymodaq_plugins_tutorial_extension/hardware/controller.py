import time
import numpy as np
from dataclasses import dataclass


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

    def __post_init__(self):
        self.calculate_base_data()

    def calculate_base_data(self):
        n_pix = self.n_pixels
        self.wavelengths = \
            np.linspace(self.wl_from, self.wl_to, n_pix)
        self.pixels = np.linspace(0, n_pix - 1, n_pix)
        self.spectrum = \
            np.exp(-((self.pixels - n_pix / 2) / (n_pix / 3))**4)
        self.absorption = \
            self.absorption \
            * np.exp(-((self.pixels - n_pix / 4) / (n_pix / 8))**2)

    def simulate_spectrum(self, shutter_open: bool, sample: bool):
        data = np.random.normal(loc=self.dark_level * self.integration_time,
                                scale=self.readout_noise, size=self.n_pixels)
        if shutter_open:
            light = self.spectrum * self.light_level * self.integration_time \
                * self.pe_per_lsb
            data += np.random.poisson(light) / self.pe_per_lsb

        max_adc = (1 << self.adc_bits) - 1
        data = np.where(data < max_adc, np.floor(data), max_adc)
        return data, time.time()


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
