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
    shutter_names = ['dark', 'excitation']

    def __post_init__(self):
        self.calculate_base_data()
        self.with_sample = True

    def calculate_base_data(self):
        n_pix = self.n_pixels
        self.wavelengths = np.linspace(self.wl_from, self.wl_to, n_pix)
        self.pixels = np.linspace(0, n_pix - 1, n_pix)
        self.spectrum = np.exp(-((self.pixels - n_pix / 2) / (n_pix / 3))**4)
        self.absorption = \
            self.absorption \
            * np.exp(-((self.pixels - n_pix / 4) / (n_pix / 8))**2)


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    spectrograph = MockSpectrograph()

    plt.plot(spectrograph.wavelengths, spectrograph.spectrum)
    plt.plot(spectrograph.wavelengths, spectrograph.absorption)
    plt.legend(['light spectrum', 'absorption'])
    plt.show()
