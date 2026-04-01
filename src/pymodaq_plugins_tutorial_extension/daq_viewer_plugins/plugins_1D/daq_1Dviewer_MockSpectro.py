import numpy as np
from pymodaq.utils.data import DataFromPlugins, DataToExport, Axis
from pymodaq_gui.parameter import Parameter
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, \
    comon_parameters, main
from pymodaq_plugins_tutorial_extension.hardware.controller import \
    MockSpectrograph


class DAQ_1DViewer_MockSpectro(DAQ_Viewer_base):
    """Simulated Spectrometer Instrument plugin class for a 1D viewer.
       Besides testing spectrometer applications, this plugin permits to
       simulate real detectors with realistic noise settings.
    """

    params = comon_parameters+[
        {'title': 'Integration time [sec]', 'name': 'integration_time',
         'type': 'float', 'min': 0.001, 'value': 1,
         'tip': 'Integration time in seconds' },
        {'title': 'Number of pixels', 'name': 'n_pixels', 'type': 'int',
         'min': 1, 'value': 500 },
        {'title': 'Wavelengths from:', 'name': 'wl_from',
         'type': 'float', 'min': 250, 'max': 450, 'value': 300 },
        {'title': 'Wavelengths to:', 'name': 'wl_to',
         'type': 'float', 'min': 450, 'max': 1500, 'value': 900 },
        {'title': 'Readout noise [LSB]', 'name': 'readout_noise',
         'type': 'float', 'min': 0, 'value': 4,
         'tip': 'Acquisition noise in LSB' },
        {'title': 'Dark level [LSB/µs]:', 'name': 'dark_level',
         'type': 'float', 'min': 0, 'value': 2e3,
         'tip': 'Dark signal per second in LSB' },
        {'title': 'Light level [LSB]', 'name': 'light_level',
         'type': 'float', 'min': 0, 'value': 32e3,
         'tip': 'Signal per second in LSB' },
        {'title': 'Conversion [PE/LSB]', 'name': 'pe_per_lsb',
         'type': 'float', 'min': 1, 'value': 18.3,
         'tip': 'Photo electrons per LSB' },
        {'title': 'ADC bits', 'name': 'adc_bits',
         'type': 'int', 'min': 10, 'max': 32, 'value': 16,
         'tip': 'Number of ADC bits' },
        {'title': 'Absorption:', 'name': 'absorption',
         'type': 'float', 'min': 0, 'value': 0.3,
         'tip': 'Simulated optical density' },
    ]

    parameter_names = [param['name'] for param in params]

    def ini_attributes(self):
        self.controller: MockSpectrograph = None
        self.x_axis = None

    def commit_settings(self, param: Parameter):
        if param.name() in self.parameter_names:
            setattr(self.controller, param.name(), param.value())

    def ini_detector(self, controller=None):
        """Detector communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only 
            one actuator/detector by controller
            (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """

        self.ini_detector_init(slave_controller=controller)

        if self.is_master:
            self.controller = MockSpectrograph()
            self.x_axis = Axis(label='Wavelength', units='nm',
                                data=self.controller.wavelengths, index=0)

        return "MockSpectro initialised", True

    def close(self):
        """Terminate the communication protocol"""

        initialized = False

    def grab_data(self, Naverage=1, **kwargs):
        """Start grabbing from the detector
        Use a synchrone acquisition (blocking function)

        Parameters
        ----------
        Naverage: int
            Number of hardware averaging.
        """

        spectrum, time_stamp = self.controller.grab_spectrum()

        dfp_spectrum = \
            DataFromPlugins(name='MockSpectro', data=[spectrum], dim='Data1D',
                            labels=['spectrum'], axes=[self.x_axis])
        dfp_time_stamp = \
            DataFromPlugins(name='TimeStamp', data=[np.array([time_stamp])],
                            dim='Data0D', labels=['time stamp'])
        
        self.dte_signal.emit(DataToExport(name='spectrum',
                                          data=[dfp_spectrum, dfp_time_stamp]))

    def stop(self):
        pass


if __name__ == '__main__':
    main(__file__)
