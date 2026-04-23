from qtpy.QtCore import Signal
from typing import Union, List, Dict
from pymodaq.control_modules.move_utility_classes import DAQ_Move_base, \
    comon_parameters_fun, main, DataActuatorType, DataActuator
from pymodaq_utils.utils import ThreadCommand
from pymodaq_gui.parameter import Parameter

IDLE               = 0
ACQUIRE_SPECTRUM   = 1
ACQUIRE_BACKGROUND = 2
ACQUIRE_REFERENCE  = 3

acquisition_modes = {'idle':       IDLE,
                     'spectrum':   ACQUIRE_SPECTRUM,
                     'background': ACQUIRE_BACKGROUND,
                     'reference':  ACQUIRE_REFERENCE }

class DAQ_Move_AcquisitionMode(DAQ_Move_base):
    """ Instrument plugin class for an actuator.
    
    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware,
        in general a python wrapper around the hardware library.

    """
    mode_changed = Signal(str)

    is_multiaxes = False
    _controller_units = '' #: Union[str, List[str]] = ['mm', 'mm']
    _epsilon = 10 # applied two times with epsilon = 0.1 getting stuck with
    # target 0 where it should be 1, bug??

    params = [
        {'name': 'acquisition_mode', 'title': 'Acquisition Mode', 'type': 'list',
         'limits': [key for key in acquisition_modes.keys()],
         'default': list(acquisition_modes.keys())[0]},
    ] + comon_parameters_fun(is_multiaxes)

    def ini_attributes(self):
        self.controller: DAQ_Move_AbsorptionMode = None

    def get_actuator_value(self):
        return acquisition_modes[self.settings['acquisition_mode']]

    def close(self):
        pass

    def commit_settings(self, param: Parameter):
        # execution doesn't get here when params are changed by configurator
        # bug or feature?
        if param.name() == 'acquisition_mode':
            self.mode_changed.emit(param.value())

    def ini_stage(self, controller=None):
        if self.is_master:
            self.controller = self
        else:
            self.controller = controller

        info = "Mock Abs Mode"
        return info, True

    def move_abs(self, value: float):
        print("asked to set to", value)
        if value < 1:
            self.settings['acquisition_mode'] = 'idle'
        elif value < 2:
            self.settings['acquisition_mode'] = 'spectrum'
        elif value < 3:
            self.settings['acquisition_mode'] = 'background'
        else:
            self.settings['acquisition_mode'] = 'reference'

        self.mode_changed.emit(self.settings['acquisition_mode'])
        self.emit_status(ThreadCommand('Update_Status',
                                       ['mode set to %d' % int(value)]))

    def move_rel(self, value: float):
        value += self.settings['acquisition_mode']
        self.move_abs(value)

    def move_home(self):
        """Call the reference method of the controller"""
        self.emit_status(ThreadCommand('Update_Status',
                                       ['Move Home not implemented']))

    def stop_motion(self):
        """Stop the actuator and emits move_done signal"""
        pass


if __name__ == '__main__':
    main(__file__)
