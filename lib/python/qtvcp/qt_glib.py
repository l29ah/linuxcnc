#!/usr/bin/env python
# vim: sts=4 sw=4 et

import _hal, hal
from PyQt4.QtCore import QObject, QTimer, pyqtSignal
import linuxcnc

class QPin(QObject, hal.Pin):
    value_changed = pyqtSignal()

    REGISTRY = []
    UPDATE = False

    def __init__(self, *a, **kw):
        QObject.__init__(self)
        hal.Pin.__init__(self, *a, **kw)
        self._item_wrap(self._item)
        self._prev = None
        self.REGISTRY.append(self)
        self.update_start()

    def update(self):
        tmp = self.get()
        if tmp != self._prev:
            self.emit('value_changed')
        self._prev = tmp

    @classmethod
    def update_all(self):
        if not self.UPDATE:
            return
        kill = []
        for p in self.REGISTRY:
            try:
                p.update()
            except:
                kill.append(p)
                print "Error updating pin %s; Removing" % p
        for p in kill:
            self.REGISTRY.remove(p)
        return self.UPDATE

    @classmethod
    def update_start(self, timeout=100):
        if QPin.UPDATE:
            return
        QPin.UPDATE = True
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all)
        self.timer.start(100)

    @classmethod
    def update_stop(self, timeout=100):
        QPin.UPDATE = False

class QComponent:
    def __init__(self, comp):
        if isinstance(comp, QComponent):
            comp = comp.comp
        self.comp = comp

    def newpin(self, *a, **kw): return QPin(_hal.component.newpin(self.comp, *a, **kw))
    def getpin(self, *a, **kw): return QPin(_hal.component.getpin(self.comp, *a, **kw))

    def exit(self, *a, **kw): return self.comp.exit(*a, **kw)

    def __getitem__(self, k): return self.comp[k]
    def __setitem__(self, k, v): self.comp[k] = v

class _QStat(QObject):
    '''Emits signals based on linuxcnc status '''
    widget_update = pyqtSignal()
    state_estop = pyqtSignal()
    state_estop_reset = pyqtSignal()
    state_on = pyqtSignal()
    state_off = pyqtSignal()
    homed = pyqtSignal(str)
    all_homed = pyqtSignal()
    not_all_homed = pyqtSignal(str)
    override_limits_changed = pyqtSignal(list)

    mode_manual = pyqtSignal()
    mode_auto = pyqtSignal()
    mode_mdi = pyqtSignal()

    interp_run = pyqtSignal()
    interp_idle = pyqtSignal()
    interp_paused = pyqtSignal()
    interp_reading = pyqtSignal()
    interp_waiting = pyqtSignal()
    jograte_changed = pyqtSignal(float)

    program_pause_changed = pyqtSignal(bool)
    optional_stop_changed = pyqtSignal(bool)
    block_delete_changed = pyqtSignal(bool)

    file_loaded = pyqtSignal(str)
    reload_display = pyqtSignal()
    line_changed = pyqtSignal(int)

    tool_in_spindle_changed = pyqtSignal(int)
    spindle_control_changed = pyqtSignal(int)
    current_feed_rate = pyqtSignal(float)
    current_x_rel_position = pyqtSignal(float)

    spindle_override_changed = pyqtSignal(float)
    feed_override_changed = pyqtSignal(float)
    rapid_override_changed = pyqtSignal(float)

    feed_hold_enabled_changed = pyqtSignal(bool)

    itime_mode = pyqtSignal(bool)
    fpm_mode = pyqtSignal(bool)
    fpr_mode = pyqtSignal(bool)
    css_mode = pyqtSignal(bool)
    rpm_mode = pyqtSignal(bool)
    radius_mode = pyqtSignal(bool)
    diameter_mode = pyqtSignal(bool)

    m_code_changed = pyqtSignal(str)
    g_code_changed = pyqtSignal(str)

    metric_mode_changed = pyqtSignal(bool)
    user_system_changed = pyqtSignal(int)

    STATES = { linuxcnc.STATE_ESTOP:       'state_estop'
             , linuxcnc.STATE_ESTOP_RESET: 'state_estop_reset'
             , linuxcnc.STATE_ON:          'state_on'
             , linuxcnc.STATE_OFF:         'state_off'
             }

    MODES  = { linuxcnc.MODE_MANUAL: 'mode_manual'
             , linuxcnc.MODE_AUTO:   'mode_auto'
             , linuxcnc.MODE_MDI:    'mode_mdi'
             }

    INTERP = { linuxcnc.INTERP_WAITING: 'interp_waiting'
             , linuxcnc.INTERP_READING: 'interp_reading'
             , linuxcnc.INTERP_PAUSED:  'interp_paused'
             , linuxcnc.INTERP_IDLE:    'interp_idle'
             }

    def __init__(self, stat = None):
        QObject.__init__(self)
        self.stat = stat or linuxcnc.stat()
        self.old = {}
        try:
            self.stat.poll()
            self.merge()
        except:
            pass
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(100)
        self.current_jog_rate = 15

    def merge(self):
        self.old['state'] = self.stat.task_state
        self.old['mode']  = self.stat.task_mode
        self.old['interp']= self.stat.interp_state
        # Only update file if call_level is 0, which
        # means we are not executing a subroutine/remap
        # This avoids emitting signals for bogus file names below 
        if self.stat.call_level == 0:
            self.old['file']  = self.stat.file
        self.old['line']  = self.stat.motion_line
        self.old['homed'] = self.stat.homed
        self.old['tool_in_spindle'] = self.stat.tool_in_spindle

        self.old['paused']= self.stat.paused
        self.old['spindle_or'] = self.stat.spindlerate
        self.old['feed_or'] = self.stat.feedrate
        self.old['rapid_or'] = self.stat.rapidrate
        self.old['feed_hold']  = self.stat.feed_hold_enabled
        self.old['g5x_index']  = self.stat.g5x_index
        self.old['spindle_enabled']  = self.stat.spindle_enabled
        self.old['spindle_direction']  = self.stat.spindle_direction
        self.old['block_delete']= self.stat.block_delete
        self.old['optional_stop']= self.stat.optional_stop
        # override limits
        or_limit_list=[]
        for i in range(0,8):
            or_limit_list.append( self.stat.axis[i]['override_limits'])
        self.old['override_limits'] = or_limit_list
        # active G codes
        active_gcodes = []
        codes =''
        for i in sorted(self.stat.gcodes[1:]):
            if i == -1: continue
            if i % 10 == 0:
                    active_gcodes.append("G%d" % (i/10))
            else:
                    active_gcodes.append("G%d.%d" % (i/10, i%10))
        for i in active_gcodes:
            codes = codes +('%s '%i)
        self.old['g_code'] = codes
        # extract specific G code modes
        itime = fpm = fpr = css = rpm = metric = False
        radius = diameter = False
        for num,i in enumerate(active_gcodes):
            if i == 'G93': itime = True
            elif i == 'G94': fpm = True
            elif i == 'G95': fpr = True
            elif i == 'G96': css = True
            elif i == 'G97': rpm = True
            elif i == 'G21': metric = True
            elif i == 'G7': diameter  = True
            elif i == 'G8': radius = True
        self.old['itime'] = itime
        self.old['fpm'] = fpm
        self.old['fpr'] = fpr
        self.old['css'] = css
        self.old['rpm'] = rpm
        self.old['metric'] = metric
        self.old['radius'] = radius
        self.old['diameter'] = diameter

        # active M codes
        active_mcodes = ''
        for i in sorted(self.stat.mcodes[1:]):
            if i == -1: continue
            active_mcodes = active_mcodes + ("M%s "%i)
            #active_mcodes.append("M%s "%i)
        self.old['m_code'] = active_mcodes

    def update(self):
        try:
            self.stat.poll()
        except:
            # Reschedule
            return True
        old = dict(self.old)
        self.merge()

        state_old = old.get('state', 0)
        state_new = self.old['state']
        if not state_old:
            if state_new > linuxcnc.STATE_ESTOP:
                self.state_estop_reset.emit()
            else:
                self.state_estop.emit()
            self.state_off.emit()
            self.interp_idle.emit()

        if state_new != state_old:
            if state_old == linuxcnc.STATE_ON and state_new < linuxcnc.STATE_ON:
                self.state_off.emit()
            self[self.STATES[state_new]].emit()
            if state_new == linuxcnc.STATE_ON:
                old['mode'] = 0
                old['interp'] = 0

        mode_old = old.get('mode', 0)
        mode_new = self.old['mode']
        if mode_new != mode_old:
            self[self.MODES[mode_new]].emit()

        interp_old = old.get('interp', 0)
        interp_new = self.old['interp']
        if interp_new != interp_old:
            if not interp_old or interp_old == linuxcnc.INTERP_IDLE:
                print "Emit", "interp_run"
                self.interp_run.emit()
            self[self.INTERP[interp_new]].emit()



        # paused
        paused_old = old.get('paused', None)
        paused_new = self.old['paused']
        if paused_new != paused_old:
            self.program_pause_changed.emit(paused_new)
        # block delete
        block_delete_old = old.get('block_delete', None)
        block_delete_new = self.old['block_delete']
        if block_delete_new != block_delete_old:
            self.block_delete_changed.emit(block_delete_new)
        # optional_stop
        optional_stop_old = old.get('optionaL_stop', None)
        optional_stop_new = self.old['optional_stop']
        if optional_stop_new != optional_stop_old:
            self.optional_stop_changed.emit(optional_stop_new)



        file_old = old.get('file', None)
        file_new = self.old['file']
        if file_new != file_old:
            # if interpreter is reading or waiting, the new file
            # is a remap procedure, with the following test we
            # partly avoid emitting a signal in that case, which would cause 
            # a reload of the preview and sourceview widgets.  A signal could
            # still be emitted if aborting a program shortly after it ran an
            # external file subroutine, but that is fixed by not updating the
            # file name if call_level != 0 in the merge() function above.
            if self.stat.interp_state == linuxcnc.INTERP_IDLE:
                self.file_loaded.emit(file_new)

        #ToDo : Find a way to avoid signal when the line changed due to 
        #       a remap procedure, because the signal do highlight a wrong
        #       line in the code
        # I think this might be fixed somewhere, because I do not see bogus line changed signals
        # when running an external file subroutine.  I tried making it not record line numbers when
        # the call level is non-zero above, but then I was not getting nearly all the signals I should
        # Moses McKnight
        line_old = old.get('line', None)
        line_new = self.old['line']
        if line_new != line_old:
            self.line_changed.emit(line_new)

        tool_old = old.get('tool_in_spindle', None)
        tool_new = self.old['tool_in_spindle']
        if tool_new != tool_old:
            self.tool_in_spindle_changed.emit(tool_new)

        # if the homed status has changed
        # check number of homed axes against number of available axes
        # if they are equal send the all_homed signal
        # else not_all_homed (with a string of unhomed joint numbers)
        # if a joint is homed send 'homed' (with a string of homed joint numbers)
        homed_old = old.get('homed', None)
        homed_new = self.old['homed']
        if homed_new != homed_old:
            axis_count = count = 0
            unhomed = homed = ""
            for i,h in enumerate(homed_new):
                if h:
                    count +=1
                    homed += str(i)
                if self.stat.axis_mask & (1<<i) == 0: continue
                axis_count += 1
                if not h:
                    unhomed += str(i)
            if count:
                self.homed.emit(homed)
            if count == axis_count:
                self.all_homed.emit()
            else:
                self.not_all_homed.emit(unhomed)

        # override limts
        or_limits_old = old.get('override_limits', None)
        or_limits_new = self.old['override_limits']
        if or_limits_new != or_limits_old:
            self.override_limits_changed.emit(or_limits_new)
        # current velocity
        self.current_feed_rate.emit(self.stat.current_vel * 60.0)
        # X relative position
        position = self.stat.actual_position[0]
        g5x_offset = self.stat.g5x_offset[0]
        tool_offset = self.stat.tool_offset[0]
        g92_offset = self.stat.g92_offset[0]
        self.current_x_rel_position.emit(position - g5x_offset - tool_offset - g92_offset)
        # spindle control
        spindle_enabled_old = old.get('spindle_enabled', None)
        spindle_enabled_new = self.old['spindle_enabled']
        spindle_direction_old = old.get('spindle_direction', None)
        spindle_direction_new = self.old['spindle_direction']
        if spindle_enabled_new != spindle_enabled_old or spindle_direction_new != spindle_direction_old:
            self.spindle_control_changed.emit( spindle_enabled_new, spindle_direction_new)
        # spindle override
        spindle_or_old = old.get('spindle_or', None)
        spindle_or_new = self.old['spindle_or']
        if spindle_or_new != spindle_or_old:
            self.spindle_override_changed.emit(spindle_or_new * 100)
        # feed override
        feed_or_old = old.get('feed_or', None)
        feed_or_new = self.old['feed_or']
        if feed_or_new != feed_or_old:
            self.feed_override_changed.emit(feed_or_new * 100)
        # rapid override
        rapid_or_old = old.get('rapid_or', None)
        rapid_or_new = self.old['rapid_or']
        if rapid_or_new != rapid_or_old:
            self.rapid_override_changed.emit(rapid_or_new * 100)
        # feed hold
        feed_hold_old = old.get('feed_hold', None)
        feed_hold_new = self.old['feed_hold']
        if feed_hold_new != feed_hold_old:
            self.feed_hold_enabled_changed.emit(feed_hold_new)
        # G5x (active user system)
        g5x_index_old = old.get('g5x_index', None)
        g5x_index_new = self.old['g5x_index']
        if g5x_index_new != g5x_index_old:
            self.user_system_changed.emit(g5x_index_new)
        # inverse time mode g93
        itime_old = old.get('itime', None)
        itime_new = self.old['itime']
        if itime_new != itime_old:
            self.itime_mode.emit(itime_new)




        # feed per minute mode g94
        fpm_old = old.get('fpm', None)
        fpm_new = self.old['fpm']
        if fpm_new != fpm_old:
            self.fpm_mode.emit(fpm_new)
        # feed per revolution mode g95
        fpr_old = old.get('fpr', None)
        fpr_new = self.old['fpr']
        if fpr_new != fpr_old:
            self.fpr_mode.emit(fpr_new)
        # css mode g96
        css_old = old.get('css', None)
        css_new = self.old['css']
        if css_new != css_old:
            self.css_mode.emit(css_new)
        # rpm mode g97
        rpm_old = old.get('rpm', None)
        rpm_new = self.old['rpm']
        if rpm_new != rpm_old:
            self.rpm_mode.emit(rpm_new)
        # radius mode g8
        radius_old = old.get('radius', None)
        radius_new = self.old['radius']
        if radius_new != radius_old:
            self.radius_mode.emit(radius_new)
        # diameter mode g7
        diam_old = old.get('diameter', None)
        diam_new = self.old['diameter']
        if diam_new != diam_old:
            self.diameter_mode.emit(diam_new)
        # M codes
        m_code_old = old.get('m_code', None)
        m_code_new = self.old['m_code']
        if m_code_new != m_code_old:
            self.m_code_changed.emit(m_code_new)
        # G codes
        g_code_old = old.get('g_code', None)
        g_code_new = self.old['g_code']
        if g_code_new != g_code_old:
            self.g_code_changed.emit(g_code_new)
        # metric mode g21
        metric_old = old.get('metric', None)
        metric_new = self.old['metric']
        if metric_new != metric_old:
            self.metric_mode_changed.emit(metric_new)
        # A widget can register for an update signal ever 100ms
        self.widget_update.emit()
        # AND DONE... Return true to continue timeout
        return True


    def forced_update(self):
        print 'forced!'
        try:
            self.stat.poll()
        except:
            # Reschedule
            return True
        self.merge()
        self.jograte_changed.emit(15)
        # override limts
        or_limits_new = self.old['override_limits']
        print 'override',or_limits_new
        self.override_limits_changed.emit(or_limits_new)
        # overrides
        feed_or_new = self.old['feed_or']
        self.feed_override_changed.emit(feed_or_new * 100)
        rapid_or_new = self.old['rapid_or']
        self.rapid_override_changed.emit(rapid_or_new  * 100)
        spindle_or_new = self.old['spindle_or']
        self.spindle_override_changed.emit(spindle_or_new  * 100)

        # spindle speed mpde
        css_new = self.old['css']
        if css_new:
            self.css_mode.emit(css_new)
        rpm_new = self.old['rpm']
        if rpm_new:
            self.rpm_mode.emit(rpm_new)

        # feed mode:
        itime_new = self.old['itime']
        if itime_new:
            self.itime_mode.emit(itime_new)
        fpm_new = self.old['fpm']
        if fpm_new:
            self.fpm_mode.emit(fpm_new)
        fpr_new = self.old['fpr']
        if fpr_new:
            self.fpr_mode.emit(fpr_new)
        # paused
        paused_new = self.old['paused']
        self.program_pause_changed.emit(paused_new)
        # block delete
        block_delete_new = self.old['block_delete']
        self.block_delete_changed.emit(block_delete_new)
        # optional_stop
        optional_stop_new = self.old['optional_stop']
        self.optional_stop_changed.emit(optional_stop_new)
        # user system G5x
        system_new = self.old['g5x_index']
        if system_new:
            self.user_system_changed.emit(system_new)
        # radius mode g8
        radius_new = self.old['radius']
        self.radius_mode.emit(radius_new)
        # diameter mode g7
        diam_new = self.old['diameter']
        self.diameter_mode.emit(diam_new)
        # M codes
        m_code_new = self.old['m_code']
        self.m_code_changed.emit(m_code_new)
        # G codes
        g_code_new = self.old['g_code']
        self.g_code_changed.emit(g_code_new)
        # metric units G21
        metric_new = self.old['metric']
        if metric_new:
            self.metric_mode_changed.emit(metric_new)
        # tool in spindle
        tool_new = self.old['tool_in_spindle']
        self.tool_in_spindle_changed.emit( tool_new)


    def set_jog_rate(self,upm):
        self.current_jog_rate = upm
        self.jograte_changed.emit(upm)

    def __getitem__(self, item):
        return getattr(self, item)
    def __setitem__(self, item, value):
        return setattr(self, item, value)

class QStat(_QStat):
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = _QStat.__new__(cls, *args, **kwargs)
        return cls._instance