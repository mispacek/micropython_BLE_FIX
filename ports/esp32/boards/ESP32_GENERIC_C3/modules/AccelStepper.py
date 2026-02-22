# AccelStepper.py
# Fast ISR-driven stepper controller for MicroPython (ESP32, RP2040)
# - Shared Timer(0), period=1ms
# - NO schedule() for stepping/math (only used to propagate CTRL+C into main thread)
# - Fixed-point Q16
# - Max speed clamp: 250 steps/s
# - Ramped response to setMaxSpeed() changes (no speed jumps)
# - No steps generated when at target (no +/- dithering)
# - Robust re-init: kills older motors that share ANY pin (GPIO 0 is valid)
# - Timer watchdog: if timer callback stops, it is restarted on next register()

FUNCTION  = 0
DRIVER    = 1
FULL2WIRE = 2
FULL3WIRE = 3
FULL4WIRE = 4
HALF3WIRE = 6
HALF4WIRE = 8
BIPOLAR4WIRE = 10
BIPOLAR_HALF4WIRE = 12

try:
    import micropython
    micropython.alloc_emergency_exception_buf(256)
    _native = micropython.native
    _has_schedule = hasattr(micropython, "schedule")
except Exception:
    micropython = None
    _has_schedule = False
    def _native(f):
        return f

import machine
import time as _time

_Q   = 16
_ONE = 1 << _Q

_MAX_SPEED_HZ = 500

_SHIFT_1000 = 20
_K_1000 = (1 << _SHIFT_1000) // 1000  # 1048

_FULL4_SEQ = (0x9, 0x3, 0x6, 0xC)
_HALF4_SEQ = (0x1, 0x3, 0x2, 0x6, 0x4, 0xC, 0x8, 0x9)
_FULL3_SEQ = (0x1, 0x2, 0x4)
_HALF3_SEQ = (0x1, 0x3, 0x2, 0x6, 0x4, 0x5)
_FULL2_SEQ = (0x1, 0x3, 0x2, 0x0)
# pin1=A1, pin2=A2, pin3=B1, pin4=B2
# A+ = 10, A- = 01; B+ = 10, B- = 01 (na příslušných párech)
_BIPOLAR_FULL4_SEQ = (0x5, 0x6, 0xA, 0x9)              # A+B+, A-B+, A-B-, A+B-
_BIPOLAR_HALF4_SEQ = (0x1, 0x5, 0x4, 0x6, 0x2, 0xA, 0x8, 0x9)




class _StepperTicker:
    _timer = None
    _motors = []
    _running = False
    _busy = False

    _hb_ms = 0
    _fault = False

    # CTRL+C propagation into main thread
    _kbi_pending = False

    @staticmethod
    def _irq_disable():
        try:
            return micropython.disable_irq()
        except Exception:
            try:
                return machine.disable_irq()
            except Exception:
                return None

    @staticmethod
    def _irq_enable(state):
        if state is None:
            return
        try:
            micropython.enable_irq(state)
        except Exception:
            try:
                machine.enable_irq(state)
            except Exception:
                pass

    @classmethod
    def _mark_hb(cls):
        cls._hb_ms = _time.ticks_ms()

    @classmethod
    def ensure_running(cls):
        now = _time.ticks_ms()
        hb = cls._hb_ms
        stale = (hb != 0) and (_time.ticks_diff(now, hb) > 50)
        if (not cls._running) or (cls._timer is None) or cls._fault or stale:
            cls.restart()

    @classmethod
    def start(cls):
        if cls._running and (cls._timer is not None):
            return
        cls._fault = False
        cls._hb_ms = _time.ticks_ms()
        cls._timer = machine.Timer(0)
        cls._running = True
        cls._timer.init(period=1, mode=machine.Timer.PERIODIC, callback=cls._cb)

    @classmethod
    def stop(cls):
        t = cls._timer
        cls._running = False
        cls._timer = None
        if t is not None:
            try:
                t.deinit()
            except Exception:
                pass

    @classmethod
    def restart(cls):
        cls.stop()
        try:
            cls.start()
        except Exception:
            cls._fault = True
            cls._running = False
            cls._timer = None

    @classmethod
    def register(cls, m):
        st = cls._irq_disable()
        try:
            cls._motors.append(m)
            cls.ensure_running()
        finally:
            cls._irq_enable(st)

    @classmethod
    def unregister(cls, m):
        st = cls._irq_disable()
        try:
            lst = cls._motors
            for i in range(len(lst) - 1, -1, -1):
                if lst[i] is m:
                    lst.pop(i)
                    break
            if not lst:
                cls.stop()
        finally:
            cls._irq_enable(st)

    @classmethod
    def kill_conflicts(cls, pins_tuple):
        if not pins_tuple:
            return
        st = cls._irq_disable()
        try:
            lst = cls._motors
            for i in range(len(lst) - 1, -1, -1):
                m = lst[i]
                mp = m._pins
                if not mp:
                    continue
                conflict = False
                for p in pins_tuple:
                    for q in mp:
                        if p == q:
                            conflict = True
                            break
                    if conflict:
                        break
                if conflict:
                    try:
                        m._force_shutdown()
                    except Exception:
                        try:
                            cls.unregister(m)
                        except Exception:
                            pass
        finally:
            cls._irq_enable(st)

    @staticmethod
    def _raise_kbi(_arg):
        # executed in main thread (via micropython.schedule)
        raise KeyboardInterrupt

    @classmethod
    def _propagate_kbi(cls):
        # Ensure timer is off, then raise in main thread.
        cls._kbi_pending = True
        try:
            cls.stop()
        except Exception:
            pass
        cls._fault = True

        if _has_schedule:
            try:
                micropython.schedule(cls._raise_kbi, 0)
            except Exception:
                # If schedule queue is full, main might still see CTRL+C on next bytecode.
                pass

    @classmethod
    @_native
    def _cb(cls, _t):
        try:
            if cls._busy:
                return
            cls._busy = True
        
            cls._mark_hb()

            motors = cls._motors
            for i in range(len(motors)):
                m = motors[i]
                if m._enabled and m._active:
                    m._tick_1ms()

        except KeyboardInterrupt:
            # IMPORTANT: propagate into main program
            cls._propagate_kbi()

        except BaseException:
            # Any other error: mark fault and stop timer so next register can restart.
            cls._fault = True
            try:
                cls.stop()
            except Exception:
                pass

        finally:
            cls._busy = False


class AccelStepper:
    __slots__ = (
        "_interface",
        "_pin1", "_pin2", "_pin3", "_pin4",
        "_set1", "_set2", "_set3", "_set4",
        "_dir", "_step", "_set_dir", "_set_step",
        "_enable_pin", "_enable_set", "_invert_enable",
        "_enabled", "_active",
        "_step_idx",
        "_pos", "_target",
        "_speed_q", "_max_speed_q",
        "_accel_q", "_accel_tick_q",
        "_phase_q",
        "_fn_fwd", "_fn_bwd",
        "_pins",
    )

    def __init__(self, interface, pin1, pin2=None, pin3=None, pin4=None,
                 enable_outputs=True, enable_pin=None, invert_enable=False,
                 forward_func=None, backward_func=None):

        self._interface = interface

        self._pin1 = self._pin2 = self._pin3 = self._pin4 = None
        self._set1 = self._set2 = self._set3 = self._set4 = None

        self._dir = None
        self._step = None
        self._set_dir = None
        self._set_step = None

        self._enable_pin = None
        self._enable_set = None
        self._invert_enable = True if invert_enable else False

        self._enabled = True
        self._active = False

        self._step_idx = 0
        self._pos = 0
        self._target = 0

        self._speed_q = 0
        self._max_speed_q = 0
        self._accel_q = 0
        self._accel_tick_q = 1

        self._phase_q = 0

        self._fn_fwd = forward_func
        self._fn_bwd = backward_func

        if interface == DRIVER:
            self._pins = (int(pin1), int(pin2))
        elif interface == FUNCTION:
            self._pins = ()
        else:
            pts = [int(pin1)]
            if pin2 is not None: pts.append(int(pin2))
            if pin3 is not None: pts.append(int(pin3))
            if pin4 is not None: pts.append(int(pin4))
            self._pins = tuple(pts)

        _StepperTicker.kill_conflicts(self._pins)
        _StepperTicker.ensure_running()

        if interface == FUNCTION:
            pass

        elif interface == DRIVER:
            self._step = machine.Pin(pin1, machine.Pin.OUT)
            self._dir  = machine.Pin(pin2, machine.Pin.OUT)
            self._set_step = self._step.value
            self._set_dir = self._dir.value
            self._set_step(0)
            self._set_dir(0)

        else:
            self._pin1 = machine.Pin(pin1, machine.Pin.OUT); self._set1 = self._pin1.value
            if pin2 is None:
                raise ValueError("pin2 required for coil interfaces")
            self._pin2 = machine.Pin(pin2, machine.Pin.OUT); self._set2 = self._pin2.value
            if pin3 is not None:
                self._pin3 = machine.Pin(pin3, machine.Pin.OUT); self._set3 = self._pin3.value
            if pin4 is not None:
                self._pin4 = machine.Pin(pin4, machine.Pin.OUT); self._set4 = self._pin4.value
            self._write_coils(0)

        if enable_pin is not None:
            self._enable_pin = machine.Pin(enable_pin, machine.Pin.OUT)
            self._enable_set = self._enable_pin.value

        if enable_outputs:
            self.enableOutputs()
        else:
            self.disableOutputs()

        self.setMaxSpeed(1)
        self.setAcceleration(1)

        _StepperTicker.register(self)

    def deinit(self):
        self._force_shutdown()

    def _force_shutdown(self):
        self.stop(hard=True)
        self.disableOutputs()
        self._active = False
        _StepperTicker.unregister(self)

    def enableOutputs(self):
        self._enabled = True
        if self._enable_set is not None:
            self._enable_set(0 if self._invert_enable else 1)

    def disableOutputs(self):
        self._enabled = False
        if self._interface == DRIVER:
            if self._set_step is not None:
                self._set_step(0)
        else:
            self._write_coils(0)
        if self._enable_set is not None:
            self._enable_set(1 if self._invert_enable else 0)

    def setMaxSpeed(self, speed):
        if speed < 0:
            speed = -speed
        if speed > _MAX_SPEED_HZ:
            speed = _MAX_SPEED_HZ
        self._max_speed_q = int(speed * _ONE)

    def setAcceleration(self, accel):
        if accel < 0:
            accel = -accel
        if accel < 1:
            accel = 1
        self._accel_q = int(accel * _ONE)
        at = (self._accel_q * _K_1000) >> _SHIFT_1000
        if at < 1:
            at = 1
        self._accel_tick_q = at

    def moveTo(self, absolute):
        self._target = int(absolute)
        self._active = True

    def move(self, relative):
        self._target = self._pos + int(relative)
        self._active = True

    def setCurrentPosition(self, pos):
        self._pos = int(pos)
        self._target = self._pos
        self._speed_q = 0
        self._phase_q = 0
        self._active = False

    def currentPosition(self):
        return self._pos

    def targetPosition(self):
        return self._target

    def distanceToGo(self):
        return self._target - self._pos

    def speed(self):
        return self._speed_q >> _Q

    def isRunning(self):
        return (self._active and (self._target != self._pos or self._speed_q != 0))

    def stop(self, hard=False):
        if hard:
            self._speed_q = 0
            self._phase_q = 0
            self._target = self._pos
            self._active = False
            return

        vq = self._speed_q
        if vq == 0:
            self._target = self._pos
            self._active = False
            return

        v_int = (vq >> _Q) if vq >= 0 else ((-vq) >> _Q)
        a_int = self._accel_q >> _Q
        if a_int < 1:
            a_int = 1
        d = (v_int * v_int) // (2 * a_int)
        if d < 1:
            d = 1
        self._target = self._pos + d if vq > 0 else self._pos - d
        self._active = True

    @_native
    def _write_coils(self, pattern):
        s1 = self._set1
        if s1 is not None: s1(1 if (pattern & 0x1) else 0)
        s2 = self._set2
        if s2 is not None: s2(1 if (pattern & 0x2) else 0)
        s3 = self._set3
        if s3 is not None: s3(1 if (pattern & 0x4) else 0)
        s4 = self._set4
        if s4 is not None: s4(1 if (pattern & 0x8) else 0)

    @_native
    def _do_step(self, step_dir):
        itf = self._interface

        if itf == DRIVER:
            sd = self._set_dir
            ss = self._set_step
            sd(1 if step_dir > 0 else 0)
            ss(1); ss(0)
            return

        if itf == FUNCTION:
            if step_dir > 0:
                fn = self._fn_fwd
                if fn is not None: fn()
            else:
                fn = self._fn_bwd
                if fn is not None: fn()
            return

        idx = self._step_idx

        if itf == FULL4WIRE:
            idx = (idx + step_dir) & 0x3
            self._step_idx = idx
            self._write_coils(_FULL4_SEQ[idx]); return

        if itf == HALF4WIRE:
            idx = (idx + step_dir) & 0x7
            self._step_idx = idx
            self._write_coils(_HALF4_SEQ[idx]); return

        if itf == FULL3WIRE:
            idx += step_dir
            if idx >= 3: idx = 0
            elif idx < 0: idx = 2
            self._step_idx = idx
            self._write_coils(_FULL3_SEQ[idx]); return

        if itf == HALF3WIRE:
            idx += step_dir
            if idx >= 6: idx = 0
            elif idx < 0: idx = 5
            self._step_idx = idx
            self._write_coils(_HALF3_SEQ[idx]); return

        if itf == FULL2WIRE:
            idx = (idx + step_dir) & 0x3
            self._step_idx = idx
            self._write_coils(_FULL2_SEQ[idx]); return
        
        if itf == BIPOLAR4WIRE:
            idx = (idx + step_dir) & 0x3
            self._step_idx = idx
            self._write_coils(_BIPOLAR_FULL4_SEQ[idx])
            return
        
        if itf == BIPOLAR_HALF4WIRE:
            idx = (idx + step_dir) & 0x7
            self._step_idx = idx
            self._write_coils(_BIPOLAR_HALF4_SEQ[idx])
            return

        self._write_coils(0)

    @_native
    def _tick_1ms(self):
        pos = self._pos
        tgt = self._target
        dist = tgt - pos

        vq = self._speed_q
        max_vq = self._max_speed_q
        aq = self._accel_q
        at = self._accel_tick_q
        phase = self._phase_q

        # at target: no steps, brake to 0
        if dist == 0:
            self._phase_q = 0
            if vq > 0:
                vq -= at
                if vq < 0: vq = 0
            elif vq < 0:
                vq += at
                if vq > 0: vq = 0
            self._speed_q = vq
            if vq == 0:
                self._active = False
            return

        dir_to = 1 if dist > 0 else -1

        if vq > 0:
            dir_v = 1
            v_int = vq >> _Q
        elif vq < 0:
            dir_v = -1
            v_int = (-vq) >> _Q
        else:
            dir_v = 0
            v_int = 0

        a_int = aq >> _Q
        if a_int < 1: a_int = 1

        dist_abs = dist if dist >= 0 else -dist
        stop_dist = (v_int * v_int) // (2 * a_int)

        if dir_v != 0 and dir_v != dir_to:
            v_target = dir_to * max_vq
        else:
            v_target = 0 if stop_dist >= dist_abs else (dir_to * max_vq)

        # ramp to v_target (prevents speed jump on setMaxSpeed)
        if vq < v_target:
            vq += at
            if vq > v_target: vq = v_target
        elif vq > v_target:
            vq -= at
            if vq < v_target: vq = v_target

        self._speed_q = vq

        # phase += v/1000 for fixed 1ms
        phase += (vq * _K_1000) >> _SHIFT_1000

        # max 250Hz => <= 0.25 step/ms => at most 1 step per tick
        if phase >= _ONE:
            if (tgt - pos) <= 0:
                self._phase_q = 0
                return
            phase -= _ONE
            pos += 1
            self._pos = pos
            self._do_step(1)
            if pos == tgt:
                self._phase_q = 0
                return

        elif phase <= -_ONE:
            if (tgt - pos) >= 0:
                self._phase_q = 0
                return
            phase += _ONE
            pos -= 1
            self._pos = pos
            self._do_step(-1)
            if pos == tgt:
                self._phase_q = 0
                return

        self._phase_q = phase


def start_shared_timer():
    _StepperTicker.start()

def stop_shared_timer():
    _StepperTicker.stop()
