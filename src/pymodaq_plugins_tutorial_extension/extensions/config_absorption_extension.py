from os import path
import numpy as np
import csv

from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq_utils.config import Config, ConfigError
from pymodaq.utils.managers.modules.utils import ModuleType
from pymodaq.utils.data import DataFromPlugins, Axis
from pymodaq_plugins_tutorial_extension.utils import Config as PluginConfig
from pymodaq_plugins_tutorial_extension.extensions.absorption_extension \
    import Absorption

logger = set_logger(get_module_name(__file__))

main_config = Config()
plugin_config = PluginConfig()

EXTENSION_NAME = 'ConfigAbsorption'
CLASS_NAME = 'ConfigAbsorption'

class ConfigAbsorption(Absorption):

    def do_things_after_experiment_set(self, experiment_name: str):
        self.modules_manager.actuators_all = \
            self.dashboard.modules_manager.actuators_all
        self.modules_manager.detectors_all = \
            self.dashboard.modules_manager.detectors_all

        self.detector = \
            self.modules_manager.get_mod_from_name('Spectrometer',
                                                   ModuleType.Detector)
        self.detector.grab_done_signal.connect(self.take_data)
        # ok here?
        self.x_axis = \
            Axis(label='Wavelength', units='nm',
                 data=self.detector.controller.wavelengths, index=0)

        self.acquisition_mode_hook = \
            self.modules_manager.get_mod_from_name('acquisition-mode',
                                                   ModuleType.Actuator)
        self.acquisition_mode_hook.controller.mode_changed\
                                        .connect(self.set_acquisition_mode)

    def take_background(self, mean, error):
        self.background = mean
        self.error_background = error
        self.have_background = True
        dfp = DataFromPlugins(name='Spectrograph',
                              data=[self.background, self.error_background],
                              dim='Data1D', labels=['background', 'error'],
                              axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)
        self.background_viewer.show_data(dfp)
        self.state_manager.entry = 'spectrum'
        self.state_manager.execute_entry()
        self.adjust_actions()

    def start_background(self):
        self.data_valid = False
        self.n_average = self.settings['back_averaging']
        self.n_samples = 0
        self.adjust_actions()
        self.state_manager.entry = 'background'
        self.state_manager.execute_entry()
        if self.state_manager.entry_applied:
            self.detector.grab()
            self.data_valid = True

    def set_acquisition_mode(self, mode: str):
        # could we have a racing condition here?
        print(f'set mode to {mode}')
        if self.acquisition_mode != mode:
            self.acquisition_mode = mode
            self.n_samples = 0
            self.data_valid = True

def main():
    from pymodaq_gui.utils.utils import mkQApp
    from pymodaq.dashboard import load_dashboard_with_experiment
    from pymodaq.utils.messenger import messagebox

    app = mkQApp(EXTENSION_NAME)
    try:
        experiment_file_name = plugin_config('experiments', f'experiment_for_{CLASS_NAME.lower()}')
        load_dashboard_with_experiment(experiment_file_name, EXTENSION_NAME)
        app.exec()

    except ConfigError as e:
        messagebox(f'No entry with name f"experiment_for_{CLASS_NAME.lower()}" has been configured'
                   f'in the plugin config file. The toml entry should be:\n'
                   f'[experiments]'
                   f"experiment_for_{CLASS_NAME.lower()} = {'a name for an existing experiment'}"
                   )


if __name__ == '__main__':
    main()
