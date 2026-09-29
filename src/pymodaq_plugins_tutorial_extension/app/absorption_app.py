import numpy as np
from qtpy import QtWidgets
from qtpy.QtCore import QSettings, QByteArray
from qtpy.QtGui import QKeySequence
from pymodaq_gui import utils as gutils
from pymodaq_utils.config import Config, get_set_config_dir
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq.utils.data import DataFromPlugins, DataToExport, Axis
from pymodaq_gui.utils.dock import DockArea
from pymodaq_gui.plotting.data_viewers.viewer1D import Viewer1D
from pymodaq.control_modules.daq_viewer import DAQ_Viewer
from pymodaq.control_modules.daq_move import DAQ_Move

from pymodaq_plugins_tutorial_extension.utils import Config as PluginConfig

logger = set_logger(get_module_name(__file__))

main_config = Config()
plugin_config = PluginConfig()

APPLICATION_NAME = 'Absorption'
CLASS_NAME = 'AbsorptionApp'


class AbsorptionApp(gutils.CustomApp):

    measurement_modes = [ 'Raw', 'Background Subtracted', 'Absorption' ]

    application_params = [
        {'name': 'measurement_mode', 'title': 'Measurement Mode',
         'type': 'list', 'limits': measurement_modes,
         'tip': 'Measurement Mode', 'value': measurement_modes[0] },
        {'name': 'back_averaging', 'title': 'Background Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 100,
         'tip': 'Background Software Averaging'},
        {'name': 'ref_averaging', 'title': 'Reference Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 100,
         'tip': 'Reference Software Averaging'},
    ]

    device_params = [
        {'name': 'integration_time', 'title': 'Integration Time [ms]',
         'type': 'float', 'min': 0.001, 'max': 10000, 'value': 50,
         'tip': 'Integration time in seconds'},
        {'name': 'averaging', 'title': 'Averaging',
         'type': 'int', 'min': 1, 'max': 1000, 'value': 10,
         'tip': 'Software Averaging'},
        ]

    params = application_params + [
        {'name': 'device_params', 'title': 'Device parameters', 'type': 'group',
         'children': device_params },
        ]

    def __init__(self, parent: gutils.DockArea, plugin, main_window=None):
        super().__init__(parent)
        self.have_background = False
        self.have_reference = False
        self.acquisition_mode = 'idle'
        self.plugin = plugin
        self.setup_ui()

        config_dir = get_set_config_dir("gui-state", user=True)
        settings_file_name = f'{config_dir}/{APPLICATION_NAME}.conf'
        self.qt_settings = QSettings(settings_file_name, QSettings.NativeFormat)
        self.read_settings(self.qt_settings)

    def quit_fun(self):
        self.write_settings(self.qt_settings)

    def setup_docks(self):
        self.docks['settings'] = gutils.Dock('Application Settings')
        self.dockarea.addDock(self.docks['settings'])
        self.docks['settings'].addWidget(self.settings_tree)

        self.spectrum_label = gutils.dock.DockLabel("Current Data")
        spectrum_dock = gutils.Dock('Data', label=self.spectrum_label)
        self.docks['spectrum'] = \
            self.dockarea.addDock(spectrum_dock, "right",
                                  self.docks['settings'])

        spectrum_widget = QtWidgets.QWidget()
        self.spectrum_viewer = Viewer1D(spectrum_widget)
        self.spectrum_viewer.toolbar.hide()
        spectrum_dock.addWidget(spectrum_widget)

        raw_data_dock = gutils.Dock('Raw Data')
        self.docks['raw-data'] = \
            self.dockarea.addDock(raw_data_dock, "bottom",
                                  self.docks['settings'])
        raw_data_widget = QtWidgets.QWidget()
        self.raw_data_viewer = Viewer1D(raw_data_widget)
        self.raw_data_viewer.toolbar.hide()

        raw_data_dock.addWidget(raw_data_widget)

        background_dock = gutils.Dock('Background')
        self.docks['background'] = \
            self.dockarea.addDock(background_dock, "bottom",
                                  self.docks['raw-data'])
        background_widget = QtWidgets.QWidget()
        self.background_viewer = Viewer1D(background_widget)
        background_dock.addWidget(background_widget)
        self.background_viewer.toolbar.hide()
#>>>
        # separate window with raw detector data
        self.daq_viewer_area = DockArea()
        self.detector = \
            DAQ_Viewer(self.daq_viewer_area, title=self.plugin)
        self.detector.daq_type = 'DAQ1D'
        self.detector.detector = self.plugin
        self.detector.init_hardware_ui()

        self.detector.settings.child('detector_settings', 'integration_time')\
            .setValue(self.settings.child('device_params')\
                      .child('integration_time').value())
        self.x_axis = None
#<<<

    def setup_actions(self):
        self.add_action('acquire', 'Acquire', 'run2',
                        "Acquire", checkable=False, toolbar=self.toolbar)
        self.add_action('stop', 'Stop', 'stop2',
                        "Stop", checkable=False, toolbar=self.toolbar)
        self.add_action('background', 'Take Background', 'brightness_3',
                        "Take Background", checkable=False,
                        toolbar=self.toolbar)
        self.add_action('reference', 'Take Reference', 'lightbulb',
                        "Take Reference", checkable=False,
                        toolbar=self.toolbar)
        self.add_action('save', 'Save', 'SaveAs', "Save current data",
                        checkable=False, toolbar=self.toolbar)        
        self._actions["stop"].setEnabled(False)
#>>>
        self.add_action('show', 'Show/hide', 'read2', "Show Hide DAQViewer",
                        checkable=True, toolbar=self.toolbar)
#<<<

    def adjust_actions(self):

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
        self._actions['save'].setEnabled(self._actions['acquire'].isEnabled())

    def connect_things(self):
        self.connect_action('acquire', self.start_acquiring)
        self.connect_action('stop', self.stop_acquiring)
        self.connect_action('background', self.start_background)
        self.connect_action('reference', self.start_reference)
        self.connect_action('save', self.save_current_data)
        self.detector.grab_done_signal.connect(self.take_data)
#>>>
        self.connect_action('show', self.show_detector)
#<<<

    def setup_menu(self, menubar: QtWidgets.QMenuBar = None):
#>>>
        file_menu = menubar.addMenu('File')
        #self.affect_to('save', file_menu)

        file_menu.addSeparator()
        self.quit_action = file_menu.addAction("Quit", QKeySequence('Ctrl+Q'))
#<<<

    def value_changed(self, param):
        if param.name() == "integration_time":
            self.detector.settings.child('detector_settings',
                                         'integration_time') \
                                  .setValue(param.value())
            if self.settings['measurement_mode'] != 'Raw':
                self.detector.stop()
            self.have_background = False
            self.have_reference = False
#>>>
            self.adjust_actions()

        if param.name() == "averaging":
            self.average = param.value()
        elif param.name() == "back_averaging":
            self.background_average = param.value()
        elif param.name() == "measurement_mode":
            self.measurement_mode = param.value()

        if hasattr(self, 'measurement_mode'):
            self.adjust_actions()
#<<<

    def write_settings(self, qt_settings):
         qt_settings.setValue("geometry", self.mainwindow.saveGeometry())
         qt_settings.setValue("dockarea", self.dockarea.saveState())
         for param in self.device_params:
             qt_settings.setValue(param['name'],
                                  self.settings.child('device_params') \
                                  [param['name']])
         for param in self.application_params:
             qt_settings.setValue(param['name'], self.settings[param['name']])

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
         for param in self.application_params:
             self.settings[param['name']] = \
                 qt_settings.value(param['name'], param['value'])

#>>>
    def show_detector(self, status):
        self.daq_viewer_area.setVisible(status)
#<<<

    def take_data(self, data: DataToExport):
        if self.x_axis is None:
            self.x_axis = \
                Axis(label='Wavelength', units='nm',
                     data=self.detector.controller.wavelengths, index=0)
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
        if self.settings['measurement_mode'] == 'Raw':
            self.show_data(self.mean_current, self.error_current, 'raw')
            return

        if self.acquisition_mode == 'acquire':
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
        dfp = DataFromPlugins(name='current',
                              data=[self.mean_current, self.error_current],
                              dim='Data1D', labels=['current', 'error'],
                              axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)

    def show_data(self, mean, error, name, raw=None, reference=None):
        dfp = DataFromPlugins(name=name, data=[mean, error], dim='Data1D',
                              labels=[name, 'error'], axes=[self.wavelengths])
        self.spectrum_viewer.show_data(dfp)
        if raw is not None:
            data = [raw]
            labels = ['raw signal']
            if reference is not None:
                data.append(reference)
                labels.append('reference')
            dfp = DataFromPlugins(name='raw', data=data, dim='Data1D',
                                  labels=labels, axes=[self.wavelengths])
            self.raw_data_viewer.show_data(dfp)

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
        self.have_reference = False
        dfp = DataFromPlugins(name='Spectrograph',
                              data=[self.background, self.error_background],
                              dim='Data1D', labels=['background', 'error'],
                              axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)
        self.background_viewer.show_data(dfp)
        self.stop_acquiring()
        self.detector.stop_grab()
        if hasattr(self.detector.controller, "set_shutter_value"):
            self.detector.controller.set_shutter_value('dark', 1200)

    def take_reference(self, mean, error):
        self.reference = mean - self.background
        self.error_reference = error
        self.reference_valid_mask = self.reference > 0
        self.have_reference = True
        self.absorption = None
        dfp = DataFromPlugins(name='Spectrograph',
                              data=[self.reference, self.error_reference],
                              dim='Data1D', labels=['reference', 'error'],
                              axes=[self.x_axis])
        self.spectrum_viewer.show_data(dfp)
        self.raw_data_viewer.show_data(dfp)
        self.detector.controller.with_sample = True
        self.stop_acquiring()
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
        self.x_axis = None
        self.n_samples = 0
        self.n_average = self.settings.child('device_params')['averaging']
        self._actions["acquire"].setEnabled(False)
        self._actions["stop"].setEnabled(True)
        self.acquisition_mode = 'acquire'
        self.adjust_actions()
        self.detector.grab()

    def start_background(self):
        if hasattr(self.detector.controller, "set_shutter_value"):
            self.detector.controller.set_shutter_value('dark', 0)
        else:
            breakpoint()
            result = \
                QtWidgets.QMessageBox.question(None, "Reference",
                                               "Close the shutter",
                                         QtWidgets.QMessageBox.StandardButton.Ok
                                  | QtWidgets.QMessageBox.StandardButton.Cancel)
            if result != QtWidgets.QMessageBox.Ok:
                return
        self.acquisition_mode = 'background'
        self.n_average = self.settings['back_averaging']
        self.n_samples = 0
        self.adjust_actions()
        self.detector.grab()

    def start_reference(self):
        result = \
            QtWidgets.QMessageBox.question(None, "Reference",
                                           "Insert a blank sample",
                                         QtWidgets.QMessageBox.StandardButton.Ok
                                  | QtWidgets.QMessageBox.StandardButton.Cancel)
        if result != QtWidgets.QMessageBox.Ok:
            return
        self.detector.controller.with_sample = False
        self.acquisition_mode = 'reference'
        self.n_average = self.settings['ref_averaging']
        self.n_samples = 0
        self.data_valid = True
        self.adjust_actions()
        self.detector.grab()

    def stop_acquiring(self):
        self.detector.stop_grab()
        self.acquisition_mode = 'idle'
        self.adjust_actions()
        self._actions["acquire"].setEnabled(True)
        self._actions["stop"].setEnabled(False)

    def save_current_data(self):
        directory = self.qt_settings.value('data-dir', None)
        if directory is None:
            directory = "."
        result = QtWidgets.QFileDialog.getSaveFileName(caption="Save Data",
                                                       dir=directory,
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

            if self.settings['measurement_mode'] == 'Background':
                writer.writerow(['wavelength', 'current data', 'current error',
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
            if not self.have_reference:
                writer.writerow(['wavelength', 'current data', 'current error',
                                 'background', 'error background'])
                for i,wl in enumerate(wavelengths):
                    writer.writerow(['%.1f' % wl, '%.3f' % self.mean_current[i],
                                     '%.1f' % self.error_current[i],
                                     '%.1f' % self.background[i],
                                     '%.1f' % self.error_background[i]])
                return
            if hasattr(self, 'absorption') and self.absorption is not None:
                writer.writerow(['wavelength', 'current data', 'current error',
                                 'background', 'error background', 'reference',
                                 'error reference', 'absorption', 'error'])
                for i,wl in enumerate(wavelengths):
                    writer.writerow(['%.1f' % wl, '%.3f' % self.mean_current[i],
                                     '%.3f' % self.error_current[i],
                                     '%.3f' % self.background[i],
                                     '%.3f' % self.error_background[i],
                                     '%.3f' % self.reference[i],
                                     '%.3f' % self.error_reference[i],
                                     '%.6f' % self.absorption[i],
                                     '%.6f' % self.error_absorption[i]])
            else:
                writer.writerow(['wavelength', 'current data', 'current error',
                                 'background', 'error background', 'reference',
                                 'error reference'])
                for i,wl in enumerate(wavelengths):
                    writer.writerow(['%.1f' % wl, '%.3f' % self.mean_current[i],
                                     '%.3f' % self.error_current[i],
                                     '%.3f' % self.background[i],
                                     '%.3f' % self.error_background[i],
                                     '%.3f' % self.reference[i],
                                     '%.3f' % self.error_reference[i]])


def main():
    from pymodaq_gui.utils.utils import mkQApp
    app = mkQApp('CustomApp')

    mainwindow = QtWidgets.QMainWindow()
    dockarea = gutils.DockArea()
    mainwindow.setCentralWidget(dockarea)

    prog = AbsorptionApp(dockarea)

    mainwindow.show()

    app.exec()


def main():
    import sys, time
    from pymodaq_gui.utils.utils import mkQApp
    from qtpy.QtCore import pyqtRemoveInputHook, QTimer
    from qtpy.QtWidgets import QSplashScreen, QMainWindow
    from qtpy.QtGui import QPixmap

    app = mkQApp('CustomApp')

    show_splash = True
    plugin = 'Avantes'

    arg_pos = 1
    while arg_pos < len(sys.argv):
        if sys.argv[arg_pos] == '--simulate':
            plugin = "MockSpectro"
        elif sys.argv[arg_pos] == '--plugin' and arg_pos < len(sys.argv) - 1:
            arg_pos += 1
            plugin=sys.argv[arg_pos]
        elif sys.argv[arg_pos] == '--no-splash':
            show_splash = False
        else:
            raise RuntimeError("command line argument error")
        arg_pos += 1

    if show_splash:
        splash_pixmap = QPixmap("splash.png")
        splash = QSplashScreen(splash_pixmap)
        splash.show()

    app = mkQApp(plugin)
    pyqtRemoveInputHook() # needed for using pdb inside the qt eventloop

    mainwindow = QMainWindow()
    dockarea = DockArea()
    mainwindow.setCentralWidget(dockarea)

    prog = AbsorptionApp(dockarea, plugin=plugin, main_window=mainwindow)
    app.lastWindowClosed.connect(prog.quit_fun)

    if show_splash:
        QTimer.singleShot(2000, splash.close)
        QTimer.singleShot(2000, mainwindow.show)
    else:
        mainwindow.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
