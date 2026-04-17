from qtpy import QtWidgets

from pymodaq_gui import utils as gutils
from pymodaq_utils.config import Config, ConfigError, get_set_config_dir
from pymodaq_utils.logger import set_logger, get_module_name

from pymodaq.utils.config import get_set_preset_path
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

    params = [
        {'name': 'device_params', 'title': 'Device parameters', 'type': 'group',
         'children': [
             {'name': 'integration_time', 'title': 'Integration Time [ms]',
              'type': 'float', 'min': 0.001, 'max': 10000, 'value': 50,
              'tip': 'Integration time in seconds'},
             {'name': 'averaging', 'title': 'Averaging',
              'type': 'int', 'min': 1, 'max': 1000, 'value': 10,
              'tip': 'Software Averaging'},
             ]
         },
        ]

    def __init__(self, parent: gutils.DockArea, dashboard):
        self.detector: DAQ_Viewer = None
        super().__init__(parent, dashboard)
        self.setup_ui()
        config_dir = get_set_config_dir("gui-state", user=True)
        settings_file_name = f'{config_dir}/{EXTENSION_NAME}.conf'
        self.qt_settings = QSettings(settings_file_name, QSettings.NativeFormat)
        self.read_settings(self.qt_settings)

    def setup_docks(self):
        self.create_dashboard_toolbar()

        self.docks['settings'] = Dock('Application Settings')
        self.dockarea.addDock(self.docks['settings'])
        self.docks['settings'].addWidget(self.settings_tree)
        
        self.spectrum_label = DockLabel("Raw Data")
        spectrum_dock = Dock('Data', label=self.spectrum_label)
        self.docks['spectrum'] = \
            self.dockarea.addDock(spectrum_dock), "right",
                                  self.docks['settings'])
        spectrum_widget = QtWidgets.QWidget()
        self.spectrum_viewer = Viewer1D(spectrum_widget)
        self.spectrum_viewer.toolbar.hide()
        spectrum_dock.addWidget(spectrum_widget)

    def read_settings(self, qt_settings):
        # @PyMoDAQxperts: is there a better better way of doing?
        geometry = qt_settings.value("geometry", QByteArray())
        self.mainwindow.restoreGeometry(geometry)
        state = qt_settings.value("dockarea", None)
        if state is not None:
            try:
                self.dockarea.restoreState(state)
            except: # pyqtgraph's state restoring is not very fail safe
                # erease inconsistent settings in case pyqtgraph trips
                qt_settings.setValue("dockarea", None)
        
    def write_settings(self, qt_settings):
        qt_settings.setValue("geometry", self.mainwindow.saveGeometry())
        qt_settings.setValue("dockarea", self.dockarea.saveState())

    def quit_fun(self):
        self.write_settings(self.qt_settings)

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
        spectro_data = data.get_data_from_dim('Data1D')[0]
        self.spectrum_viewer.show_data(spectro_data)

    def do_things_after_preset_set(self, preset_name: str):
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

    def setup_actions(self):
        self.add_action('acquire', 'Acquire', 'run2',
                        "Acquire", checkable=False, toolbar=self.toolbar)
        self.add_action('stop', 'Stop', 'stop2',
                        "Stop", checkable=False, toolbar=self.toolbar)
        self._actions["stop"].setEnabled(False)

    def connect_things(self):
        self.connect_action('acquire', self.start_acquiring)
        self.connect_action('stop', self.stop_acquiring)

    def start_acquiring(self):
        self._actions["acquire"].setEnabled(False)
        self._actions["stop"].setEnabled(True)
        self.detector.grab()

    def stop_acquiring(self):
        self._actions["acquire"].setEnabled(True)
        self._actions["stop"].setEnabled(False)
        self.detector.stop_grab()

    def setup_menu(self, menubar: QtWidgets.QMenuBar = None):
        return
        file_menu = self.mainwindow.menuBar().addMenu('File')
        self.affect_to('save', file_menu)
        file_menu.addSeparator()
        #self.affect_to('quit', file_menu)

    def value_changed(self, param):
        return
        if param.name() == "integration_time":
            self.detector.settings.child('detector_settings',
                                         'integration_time') \
                                  .setValue(param.value())
            # background and reference should be measurement with the same i.t.
            if self.measurement_mode in [WITH_BACKGROUND, ABSORPTION]:
                self.detector.stop()
            self.have_background = False
            self.have_reference = False
        elif param.name() == "averaging":
            self.average = param.value()
        elif param.name() == "pymo_averaging":
            self.detector.settings.child('main_settings', 'Naverage') \
                                         .setValue(param.value())
        elif param.name() == "back_averaging":
            self.background_average = param.value()
        elif param.name() == "measurement_mode":
            self.measurement_mode = self.measurement_modes[param.value()]

        if hasattr(self, 'measurement_mode'):
            self.adjust_operation()
            self.adjust_actions()

    def adjust_actions(self):
        """Disable actions which need other actions to be performed first.
        A reference can only be taken when a background has been measured.
        Acquisition in absorption mode needs a reference (and therefore also
        a background).
        """
        if self.measurement_mode == RAW:
            self._actions["acquire"].setEnabled(True)
            self._actions["background"].setEnabled(False)
            self._actions["reference"].setEnabled(False)
        if self.measurement_mode == WITH_BACKGROUND:
            self._actions["acquire"].setEnabled(self.have_background)
            self._actions["background"].setEnabled(True)
            self._actions["reference"].setEnabled(False)
        if self.measurement_mode == ABSORPTION:
            self._actions["acquire"].setEnabled(self.have_reference)
            self._actions["background"].setEnabled(True)
            self._actions["reference"].setEnabled(self.have_background)


def main():
    from pymodaq_gui.utils.utils import mkQApp
    from pymodaq.dashboard import load_dashboard_with_preset
    from pymodaq.utils.messenger import messagebox

    from qtpy.QtCore import removeInputHook

    app = mkQApp(EXTENSION_NAME)
    try:
        preset_file_name = plugin_config('presets', f'preset_for_{CLASS_NAME.lower()}')
        load_dashboard_with_preset(preset_file_name, EXTENSION_NAME)
        app.exec()

    except ConfigError as e:
        messagebox(f'No entry with name f"preset_for_{CLASS_NAME.lower()}" has been configured'
                   f'in the plugin config file. The toml entry should be:\n'
                   f'[presets]'
                   f"preset_for_{CLASS_NAME.lower()} = {'a name for an existing preset'}"
                   )


if __name__ == '__main__':
    main()
