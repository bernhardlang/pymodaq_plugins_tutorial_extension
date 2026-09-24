import numpy as np
from qtpy.QtCore import QSettings, QByteArray
from qtpy import QtWidgets
from pymodaq_gui import utils as gutils
from pymodaq_gui.plotting.data_viewers import Viewer1D
from pymodaq_utils.config import Config, ConfigError, get_set_config_dir
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq.utils.managers.modules import ModuleType
from pymodaq.extensions.utils import CustomExt
from pymodaq.utils.data import DataFromPlugins, DataToExport, Axis
from pymodaq_plugins_tutorial_extension.utils import Config as PluginConfig

logger = set_logger(get_module_name(__file__))

main_config = Config()
plugin_config = PluginConfig()

# todo: modify this as you wish
EXTENSION_NAME = 'Absorption'
CLASS_NAME = 'AbsorptionExtension'


class AbsorptionExtension(CustomExt):

    device_params = [
        {'name': 'integration_time', 'title': 'Integration Time [ms]',
         'type': 'float', 'min': 0.001, 'max': 10000, 'value': 50,
         'tip': 'Integration time in seconds'},
        {'name': 'averaging', 'title': 'Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 10,
         'tip': 'Software Averaging'},
        ]

    params = [
        {'name': 'device_params', 'title': 'Device parameters', 'type': 'group',
         'children': device_params },
        ]

    def __init__(self, parent: gutils.DockArea, dashboard):
        super().__init__(parent, dashboard)
        self.setup_ui()
        config_dir = get_set_config_dir("gui-state", user=True)
        settings_file_name = f'{config_dir}/{EXTENSION_NAME}.conf'
        self.qt_settings = QSettings(settings_file_name, QSettings.NativeFormat)
        self.read_settings(self.qt_settings)

    def quit_fun(self):
        self.write_settings(self.qt_settings)

    def setup_docks_and_widgets(self):
        self.docks['settings'] = gutils.Dock('Application Settings')
        self.dockarea.addDock(self.docks['settings'])
        self.docks['settings'].addWidget(self.settings_tree)

        self.spectrum_label = gutils.dock.DockLabel("Raw Data")
        spectrum_dock = gutils.Dock('Data', label=self.spectrum_label)
        self.docks['spectrum'] = \
            self.dockarea.addDock(spectrum_dock, "right",
                                  self.docks['settings'])

        spectrum_widget = QtWidgets.QWidget()
        self.spectrum_viewer = Viewer1D(spectrum_widget)
        self.spectrum_viewer.toolbar.hide()
        spectrum_dock.addWidget(spectrum_widget)

    def setup_menus_and_toolbars(self, menubar: QtWidgets.QMenuBar = None):
        """Non mandatory method to be subclassed in order to create a menubar

        create menu for actions contained into the self._actions, for instance:

        Examples
        --------
        >>>file_menu = menubar.addMenu('File')
        >>>self.affect_to('load', file_menu)
        >>>self.affect_to('save', file_menu)

        >>>file_menu.addSeparator()
        >>>self.affect_to('quit', file_menu)

        See Also
        --------
        pymodaq.utils.managers.action_manager.ActionManager
        """
        # todo create and populate menu using actions defined above in self.setup_actions
        self.create_dashboard_toolbar(add_break=False)

    def setup_actions(self):
        self.add_action('acquire', 'Acquire', 'run2',
                        "Acquire", checkable=False, toolbar=self.toolbar)
        self.add_action('stop', 'Stop', 'stop2',
                        "Stop", checkable=False, toolbar=self.toolbar)
        self._actions["stop"].setEnabled(False)

    def connect_things(self):
        self.connect_action('acquire', self.start_acquiring)
        self.connect_action('stop', self.stop_acquiring)

    def value_changed(self, param):
        if param.name() == "integration_time":
            self.detector.settings.child('detector_settings',
                                         'integration_time') \
                                  .setValue(param.value())

    def do_things_after_experiment_set(self, experiment_name: str):
        self.modules_manager.detectors_all = \
            self.dashboard.modules_manager.detectors_all

        self.detector = \
            self.modules_manager.get_mod_from_name('Spectrometer',
                                                   ModuleType.Detector)
        self.detector.grab_done_signal.connect(self.take_data)
        self.x_axis = \
            Axis(label='Wavelength', units='nm',
                 data=self.detector.controller.wavelengths, index=0)

    def write_settings(self, qt_settings):
         qt_settings.setValue("geometry", self.mainwindow.saveGeometry())
         qt_settings.setValue("dockarea", self.dockarea.saveState())
         for param in self.device_params:
             qt_settings.setValue(param['name'],
                                  self.settings.child('device_params') \
                                  [param['name']])

    def read_settings(self, qt_settings):
         geometry = self.qt_settings.value("geometry", QByteArray())
         self.mainwindow.restoreGeometry(geometry)
         state = self.qt_settings.value("dockarea", None)
         if state is not None:
             try:
                 self.dockarea.restoreState(state)
             except: # pyqtgraph's state restoring is not very fail safe
                 # erase inconsistent settings in case pyqtgraph trips
                 self.qt_settings.setValue("dockarea", None)
         for param in self.device_params:
             self.settings.child('device_params')[param['name']] = \
                 qt_settings.value(param['name'], param['value'])

    def take_data(self, data: DataToExport):
        spectro_data = data.get_data_from_dim('Data1D')[0]
        self.n_samples = self.accumulate_data(spectro_data[0], self.n_samples)
        if self.n_samples < self.n_average:
            return

        if self.n_average < 2:
            self.spectrum_viewer.show_data(spectro_data)
            return

        self.mean_current, self.error_current = \
            self.average_data(self.sum_data, self.squares_data, self.n_samples)
        self.n_samples = 0
        dfp = DataFromPlugins(name='current',
                              data=[self.mean_current, self.error_current],
                              dim='Data1D', labels=['current', 'error'],
                              axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)

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

    def start_acquiring(self):
        self.n_samples = 0
        self.n_average = self.settings.child('device_params')['averaging']
        self._actions["acquire"].setEnabled(False)
        self._actions["stop"].setEnabled(True)
        self.detector.grab()

    def stop_acquiring(self):
        self.detector.stop_grab()
        self._actions["acquire"].setEnabled(True)
        self._actions["stop"].setEnabled(False)


def main():
    import sys
    from pymodaq_gui.qt_utils import mkQApp
    from pymodaq.dashboard import create_load_dashboard
    from pymodaq.utils.gui_utils.loader_utils import create_extension

    app = mkQApp('Custom Ext')

    win, dashboard = create_load_dashboard()
    win.mainwindow.setVisible(False)

    win_ext, ext = create_extension(dashboard, AbsorptionExtension)
    win_ext.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
