from qtpy import QtWidgets
from pymodaq_gui import utils as gutils
from pymodaq_gui.plotting.data_viewers import Viewer1D
from pymodaq_utils.config import Config, ConfigError
from pymodaq_utils.logger import set_logger, get_module_name
from pymodaq.utils.managers.modules import ModuleType
from pymodaq.extensions.utils import CustomExt
from pymodaq.utils.data import DataToExport, Axis
from pymodaq_plugins_tutorial_extension.utils import Config as PluginConfig

logger = set_logger(get_module_name(__file__))

main_config = Config()
plugin_config = PluginConfig()

# todo: modify this as you wish
EXTENSION_NAME = 'Absorption'
CLASS_NAME = 'AbsorptionExtension'


# todo: modify the name of this class to reflect its application and change the name in the main
# method at the end of the script
class AbsorptionExtension(CustomExt):

    def __init__(self, parent: gutils.DockArea, dashboard):
        super().__init__(parent, dashboard)
        self.setup_ui()

    def setup_docks_and_widgets(self):
        self.spectrum_label = gutils.dock.DockLabel("Raw Data")
        spectrum_dock = gutils.Dock('Data', label=self.spectrum_label)
        self.docks['spectrum'] = self.dockarea.addDock(spectrum_dock)
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
        """ Actions to perform when one of the param's value in self.settings is changed from the
        user interface

        For instance:
        if param.name() == 'do_something':
            if param.value():
                print('Do something')
                self.settings.child('main_settings', 'something_done').setValue(False)

        Parameters
        ----------
        param: (Parameter) the parameter whose value just changed
        """
        pass

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

    def take_data(self, data: DataToExport):
        spectro_data = data.get_data_from_dim('Data1D')[0]
        self.spectrum_viewer.show_data(spectro_data)

    def start_acquiring(self):
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
