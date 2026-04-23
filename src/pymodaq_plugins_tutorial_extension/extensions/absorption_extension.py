from os import path
import numpy as np
import csv
from qtpy.QtWidgets import QMenuBar, QWidget, QMessageBox, QFileDialog

from pymodaq_gui import utils as gutils
from pymodaq_utils.config import Config, ConfigError, get_set_config_dir
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq.utils.config import get_set_experiment_path
from pymodaq.extensions.custom_ext import CustomExt

from pymodaq.utils.managers.modules.utils import ModuleType
from pymodaq_gui.utils.dock import DockArea, Dock
from pyqtgraph.dockarea import DockLabel
from pymodaq_gui.plotting.data_viewers.viewer1D import Viewer1D
from pymodaq.utils.data import DataFromPlugins, Axis
from pymodaq.utils.data import DataToExport

from pymodaq_plugins_tutorial_extension.utils import Config as PluginConfig

from qtpy.QtCore import QSettings, QByteArray


logger = set_logger(get_module_name(__file__))

main_config = Config()
plugin_config = PluginConfig()

EXTENSION_NAME = 'Absorption'
CLASS_NAME = 'Absorption'

class Absorption(CustomExt):

    measurement_modes = [ 'Raw', 'Background Subtracted', 'Absorption' ]

    device_params = [
        {'name': 'integration_time', 'title': 'Integration Time [ms]',
         'type': 'float', 'min': 0.001, 'max': 10000, 'value': 50,
         'tip': 'Integration time in seconds'},
        {'name': 'averaging', 'title': 'Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 10,
         'tip': 'Software Averaging'},
        ]

    application_params = [
        {'name': 'measurement_mode', 'title': 'Measurement Mode',
         'type': 'list', 'limits': measurement_modes,
         'value': measurement_modes[0], 'tip': 'Measurement Mode'},
        {'name': 'back_averaging', 'title': 'Background Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 100,
         'tip': 'Background Software Averaging'},
        {'name': 'ref_averaging', 'title': 'Reference Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 100,
         'tip': 'Reference Software Averaging'},
        ]

    params = application_params + [
         {'name': 'device_params', 'title': 'Device parameters', 'type': 'group',
         'children': device_params },
        ]

    def __init__(self, parent: gutils.DockArea, dashboard):
        self.detector: DAQ_Viewer = None
        super().__init__(parent, dashboard)
        self.have_background = False
        self.have_reference = False
        self.acquisition_mode = 'idle'
        self.data_valid = False
        self.setup_ui()
        config_dir = get_set_config_dir("gui-state", user=True)
        settings_file_name = f'{config_dir}/{EXTENSION_NAME}.conf'
        self.qt_settings = QSettings(settings_file_name, QSettings.NativeFormat)
        self.read_settings(self.qt_settings)

    def setup_docks_and_widgets(self):
        self.create_dashboard_toolbar()

        self.docks['settings'] = Dock('Application Settings')
        self.dockarea.addDock(self.docks['settings'])
        self.docks['settings'].addWidget(self.settings_tree)

        self.spectrum_label = DockLabel("Current Data")
        spectrum_dock = Dock('Data', label=self.spectrum_label)
        self.docks['spectrum'] = \
            self.dockarea.addDock(spectrum_dock, "right",
                                  self.docks['settings'])
        spectrum_widget = QWidget()
        self.spectrum_viewer = Viewer1D(spectrum_widget)
        self.spectrum_viewer.toolbar.hide()
        spectrum_dock.addWidget(spectrum_widget)

        # plot for raw spectrum data and reference 
        raw_data_dock = Dock('Raw Data')
        self.docks['raw-data'] = \
            self.dockarea.addDock(raw_data_dock, "bottom",
                                  self.docks['settings'])
        raw_data_widget = QWidget()
        self.raw_data_viewer = Viewer1D(raw_data_widget)
        self.raw_data_viewer.toolbar.hide()

        raw_data_dock.addWidget(raw_data_widget)

        # plot for background 
        background_dock = Dock('Background')
        self.docks['background'] = \
            self.dockarea.addDock(background_dock, "bottom",
                                  self.docks['raw-data'])
        background_widget = QWidget()
        self.background_viewer = Viewer1D(background_widget)
        background_dock.addWidget(background_widget)
        self.background_viewer.toolbar.hide()

        # @PyMoDAQxperts: is there a better better way of handling settings
        # storage?
    def read_settings(self, qt_settings):
        geometry = qt_settings.value("geometry", QByteArray())
        self.mainwindow.restoreGeometry(geometry)
        state = qt_settings.value("dockarea", None)
        if state is not None:
            try:
                self.dockarea.restoreState(state)
            except: # pyqtgraph's state restoring is not very fail safe
                # erease inconsistent settings in case pyqtgraph trips
                qt_settings.setValue("dockarea", None)

        for param in self.device_params:
            self.settings.child('device_params')[param['name']] = \
                qt_settings.value(param['name'], param['value'])
        for param in self.application_params:
            self.settings[param['name']] = \
                qt_settings.value(param['name'], param['value'])
        
    def write_settings(self, qt_settings):
        qt_settings.setValue("geometry", self.mainwindow.saveGeometry())
        qt_settings.setValue("dockarea", self.dockarea.saveState())
        for param in self.device_params:
            name = param['name']
            qt_settings.setValue(name, 
                                 self.settings.child('device_params')[name])
        for param in self.application_params:
            qt_settings.setValue(name, self.settings[param['name']])

    def quit_fun(self):
        self.write_settings(self.qt_settings)

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

        self.dark_shutter = \
            self.modules_manager.get_mod_from_name('dark-shutter',
                                                    ModuleType.Actuator)
        self.dark_shutter.move_done_signal.connect(self.shutter_ready)

    def setup_actions(self):
        self.add_action('acquire', 'Acquire', 'run2',
                        "Acquire", checkable=False, toolbar=self.toolbar)
        self.add_action('stop', 'Stop', 'stop2',
                        "Stop", checkable=False, toolbar=self.toolbar)
        self.add_action('background', 'Take Background', 'brightness_3',
                        "Take Background", checkable=False, toolbar=self.toolbar)
        self.add_action('reference', 'Take Reference', 'lightbulb',
                        "Take Reference", checkable=False, toolbar=self.toolbar)
        self.add_action('save', 'Save Current', '',
                        "Save Current", checkable=False, toolbar=self.toolbar)
        self.adjust_actions()

    def connect_things(self):
        self.connect_action('acquire', self.start_acquiring)
        self.connect_action('stop', self.stop_acquiring)
        self.connect_action('background', self.start_background)
        self.connect_action('reference', self.start_reference)
        self.connect_action('save', self.save_current_data)

    def value_changed(self, param):
        if param.name() == "integration_time":
            self.detector.settings.child('detector_settings',
                                         'integration_time') \
                                  .setValue(param.value())
            # background and reference should be measurement with the same i.t.
            if self.settings['measurement_mode'] != 'Raw':
                self.detector.stop()
            self.have_background = False
            self.have_reference = False
        self.adjust_actions()

    def accumulate_data(self, data, n_samples):
        if n_samples:
            self.sum_data += data
            self.squares_data += data**2
        else:
            self.sum_data = data
            self.squares_data = data**2
        return n_samples + 1

    def average_data(self, sum_data, squares_data, n_samples):
        mean = sum_data / n_samples
        error = np.sqrt((n_samples * squares_data - sum_data**2)
                        / (n_samples**2 * (n_samples - 1)))
        return mean, error

    def take_data(self, data: DataToExport):
        if not self.data_valid:
            return

        spectro_data = data.get_data_from_dim('Data1D')[0]
        self.n_samples = self.accumulate_data(spectro_data[0], self.n_samples)
        if self.n_samples < self.n_average:
            return

        if self.n_average < 2:
            self.spectrum_viewer.show_data(spectro_data)
            return

        self.mean_current, self.error_current = \
            self.average_data(self.sum_data, self.squares_data,
                              self.n_samples)
        self.n_samples = 0

        if self.settings['measurement_mode'] == 'Raw':
            self.show_data(self.mean_current, self.error_current, 'raw')
            return

        if self.acquisition_mode == 'normal':
            self.take_normal(self.mean_current, self.error_current)
        else:
            self.data_valid = False
            self.detector.stop_grab()
            am = self.acquisition_mode
            self.acquisition_mode = 'idle'
            if am == 'background':
                self.take_background(self.mean_current, self.error_current)
            else:
                self.take_reference(self.mean_current, self.error_current)

    def take_normal(self, mean, error):
        self.mean_signal = mean - self.background

        if self.settings['measurement_mode'] == 'Background Subtracted':
            self.error_signal = np.sqrt(error**2 + self.error_background**2)
            self.show_data(self.mean_signal, error, 'signal', self.mean_signal)
        else: # self.settings['measurement_mode'] == ABSORPTION:
            valid_mask = \
                np.logical_and(self.mean_signal > 0, self.reference_valid_mask)
            self.absorption = \
                np.where(valid_mask,
                         -np.log10(self.mean_signal / self.reference), 0)
            self.error_absorption = \
                1 / np.log(10) \
                * np.sqrt((error / self.mean_signal)**2
                          + ((self.error_reference + self.error_background)
                             / self.reference)**2
                          + (1 / self.mean_signal - 1 / self.reference)**2
                            * self.error_background)

            self.show_data(self.absorption, self.error_absorption, 'absorption',
                           self.mean_signal, self.reference)

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
        self.dark_shutter.move_abs(1200)

    def take_reference(self, mean, error):
        self.reference = mean - self.background
        self.error_reference = error
        self.reference_valid_mask = self.reference > 0
        self.have_reference = True
        dfp = DataFromPlugins(name='Spectrograph',
                              data=[self.reference, self.error_reference],
                              dim='Data1D', labels=['reference', 'error'],
                              axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)
        self.raw_data_viewer.show_data(dfp)
        try:
            self.detector.controller.with_sample = True
        except:
            pass
        self.adjust_actions()

    def show_data(self, mean, error, name, raw=None, reference=None):
        dfp = DataFromPlugins(name=name, data=[mean, error], dim='Data1D',
                              labels=[name, 'error'], axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)
        if raw is not None:
            data = [raw]
            labels = ['raw signal']
            if reference is not None:
                data.append(reference)
                labels.append('reference')
            dfp = DataFromPlugins(name='raw', data=data, dim='Data1D',
                                  labels=labels, axes=[self.x_axis])
            self.raw_data_viewer.show_data(dfp)

    def start_acquiring(self):
        self.n_samples = 0
        self.data_valid = True
        self.acquisition_mode = 'normal'
        self.adjust_actions()
        self.n_average = self.settings.child('device_params')['averaging']
        self.detector.grab()

    def stop_acquiring(self):
        self.data_valid = False
        self.detector.stop_grab()
        self.acquisition_mode = 'idle'
        self.adjust_actions()

    def start_background(self):
        self.data_valid = False
        self.acquisition_mode = 'background'
        self.n_average = self.settings['back_averaging']
        self.n_samples = 0
        self.adjust_actions()
        self.dark_shutter.move_abs(0)

    def start_reference(self):
        result = \
            QMessageBox.question(None, "Reference", "Insert a blank sample",
                                 QMessageBox.StandardButton.Ok
                                 | QMessageBox.StandardButton.Cancel)
        if result != QMessageBox.Ok:
            return
        try:
            self.detector.controller.with_sample = False
        except:
            pass
        self.acquisition_mode = 'reference'
        self.n_average = self.settings['ref_averaging']
        self.n_samples = 0
        self.data_valid = True
        self.adjust_actions()
        self.detector.grab()

    def shutter_ready(self):
        self.data_valid = True
        if self.acquisition_mode == 'background':
            self.detector.grab()
        else: # idle mode
            self.adjust_actions()

    def adjust_actions(self):

        # acquire, back, ref
        action_states = {
            'Raw': [True, False, False],
            'Background Subtracted': [self.have_background, True, False],
            'Absorption': [ self.have_reference, True, self.have_background],
            'Busy': [False, False, False]
            }

        is_idle = self.acquisition_mode == 'idle'
        mode = self.settings['measurement_mode'] if is_idle else 'Busy'

        self.docks['settings'].setEnabled(is_idle)
        self._actions["stop"].setEnabled(not is_idle)
        for name,state in zip(["acquire", "background", "reference"],
                              action_states[mode]):
            self._actions[name].setEnabled(state)

    def save_current_data(self):
        """Save dat currently displayed on the main plot."""
        directory = self.qt_settings.value('data-dir', None)
        if directory is None:
            directory = "."
        result = QFileDialog.getSaveFileName(caption="Save Data", dir=directory,
                                             filter="*.csv")
        if result is None or not len(result[0]):
            return

        self.qt_settings.setValue('data-dir', path.dirname(result[0]))

        wavelengths = self.detector.controller.wavelengths
        with open(result[0], "wt") as csv_file:
            writer = csv.writer(csv_file, delimiter=',',
                                quotechar='|', quoting=csv.QUOTE_MINIMAL)
            if self.settings['measurement_mode'] == 'Raw' \
               or not self.have_background:
                writer.writerow(['wavelength', 'raw data', 'error'])
                for i,wl in enumerate(wavelengths):
                    writer.writerow(['%.1f' % wl, '%.3f' % self.mean_current[i],
                                    '%.3f' % self.error_current[i]])
                return

            if self.settings['measurement_mode']== 'Background Subtracted' \
               or not self.have_reference:
                writer.writerow(['wavelength', 'raw data', 'error raw',
                                 'background', 'error background',
                                 'background subtracted', 'error'])
                for i,wl in enumerate(wavelengths):
                    writer.writerow(['%.1f' % wl, '%.3f' % self.mean_current[i],
                                     '%.1f' % self.error_current[i],
                                     '%.1f' % self.background[i],
                                     '%.1f' % self.error_background[i],
                                     '%.1f' % self.mean_signal[i],
                                     '%.1f' % self.error_signal[i]])
                return

            # self.settings['measurement_mode'] == 'Absorption'
            writer.writerow(['wavelength', 'raw data', 'error raw', 'background',
                             'error background', 'reference', 'error reference',
                             'absorption', 'error'])
            for i,wl in enumerate(wavelengths):
                writer.writerow(['%.1f' % wl, '%.3f' % self.mean_current[i],
                                 '%.3f' % self.error_current[i],
                                 '%.3f' % self.background[i],
                                 '%.3f' % self.error_background[i],
                                 '%.3f' % self.reference[i],
                                 '%.3f' % self.error_reference[i],
                                 '%.6f' % self.absorption[i],
                                 '%.6f' % self.error_absorption[i]])

    def setup_menu(self, menubar: QMenuBar = None):
        file_menu = self.mainwindow.menuBar().addMenu('File')
        # broken in dev, setup_actions is called after setup_menu
        # self.affect_to('save', file_menu)

        file_menu.addSeparator()


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
