from pymodaq.control_modules.move_utility_classes import DAQ_Move_base, \
    comon_parameters_fun, main, DataActuatorType, DataActuator
from pymodaq_utils.utils import ThreadCommand
from pymodaq_gui.parameter import Parameter
from pymodaq_plugins_tutorial_extension.hardware.controller \
    import MockSpectrograph


class DAQ_Move_MockShutter(DAQ_Move_base):

    is_multiaxes = True
    _axis_names = MockSpectrograph.shutter_names[:2]
    _controller_units = '' #: Union[str, List[str]] = ['mm', 'mm']
    _epsilon = 0.1
    data_actuator_type = DataActuatorType.DataActuator

    params = [
    ] + comon_parameters_fun(is_multiaxes, _axis_names, epsilon=_epsilon)

    def ini_attributes(self):
        self.controller: MockTAController = None

    def get_actuator_value(self):
        axis = self.settings['multiaxes', 'axis']
        pos = DataActuator(data=self.controller.get_shutter_value(axis),
                           units=self.axis_unit)
        pos = self.get_position_with_scaling(pos)
        return pos

    def close(self):
        pass

    def commit_settings(self, param: Parameter):
        pass

    def ini_stage(self, controller=None):
        if self.is_master:
            self.controller = MockSpectrograph()
        else:
            self.controller = controller

        info = "Mock polarizer line initialised"
        return info, True

    def move_abs(self, value: DataActuator):
        value = self.check_bound(value)
        self.target_value = value
        value = self.set_position_with_scaling(value)
        axis = self.settings['multiaxes', 'axis']
        self.controller.set_shutter_value(axis, value.value(self.axis_unit))
        self.emit_status(ThreadCommand('Update_Status',
                                       ['Moved shutter %s' % axis]))

    def move_rel(self, value: DataActuator):
        axis = self.settings['multiaxes', 'axis']
        self.move_abs(self.get_actuator_value(axis) + value)

    def move_home(self):
        self.emit_status(ThreadCommand('Update_Status',
                                       ['Move Home not implemented']))

    def stop_motion(self):
        self.move_done()


if __name__ == '__main__':
    main(__file__)
