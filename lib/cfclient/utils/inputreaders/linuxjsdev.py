# -*- coding: utf8 -*-
#     ||
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2011-2013 Bitcraze AB
#
#  Crazyflie Nano Quadcopter Client
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

"""
Linux joystick driver using the Linux input_joystick subsystem. Requires sysfs
to be mounted on /sys and /dev/input/js* to be readable.

This module is very linux specific but should work on any CPU platform
"""

import sys
if not sys.platform.startswith('linux'):
    raise Exception("Only supported on Linux")

import struct
import glob
import os
import ctypes
import fcntl
import logging

logger = logging.getLogger(__name__)

__author__ = 'Bitcraze AB'
__all__ = ['Joystick']

JS_EVENT_FMT = "@IhBB"
JE_TIME = 0
JE_VALUE = 1
JE_TYPE = 2
JE_NUMBER = 3

JS_EVENT_BUTTON = 0x001
JS_EVENT_AXIS = 0x002
JS_EVENT_INIT = 0x080

#ioctls
JSIOCGAXES = 0x80016a11
JSIOCGBUTTONS = 0x80016a12

MODULE_MAIN = "Joystick"
MODULE_NAME = "Joystick"

class JEvent(object):
    """
    Joystick event class. Encapsulate single joystick event.
    """
    def __init__(self, evt_type, number, value):
        self.type = evt_type
        self.number = number
        self.value = value

    def __repr__(self):
        return "JEvent(type={}, number={}, value={})".format(self.type,
                   self.number, self.value)

#Constants
TYPE_BUTTON = 1
TYPE_AXIS = 2

class Joystick():
    """
    Linux jsdev implementation of the Joystick class
    """

    def __init__(self):
        self.opened = False
        self.buttons = []
        self.axes = []
        self.jsfile = None
        self.device_id = -1
        self.inputMap = None
        self._prev_pressed = {}

    def devices(self):
        """
        Returns a dict with device_id as key and device name as value of all
        the detected devices.
        """
        devices = []

        syspaths = glob.glob("/sys/class/input/js*")

        for path in syspaths:
            device_id = int(os.path.basename(path)[2:])
            with open(path + "/device/name") as namefile:
                name = namefile.read().strip()
            devices.append({"id": device_id, "name": name})

        return devices

    def open(self, device_id):
        """
        Open the joystick device. The device_id is given by available_devices
        """
        if self.opened and device_id != self.device_id:
            # TODO: Don't open a device twice!
            raise Exception("A joystick is already opened")

        self.device_id = device_id

        self.jsfile = open("/dev/input/js{}".format(self.device_id), "r")
        fcntl.fcntl(self.jsfile.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)

        #Get number of axis and button
        val = ctypes.c_int()
        if fcntl.ioctl(self.jsfile.fileno(), JSIOCGAXES, val) != 0:
            self.jsfile.close()
            raise Exception("Failed to read number of axes")
        self.axes = list(0 for i in range(val.value))

        if fcntl.ioctl(self.jsfile.fileno(), JSIOCGBUTTONS, val) != 0:
            self.jsfile.close()
            raise Exception("Failed to read number of axes")
        self.buttons = list(0 for i in range(val.value))

        self.__initvalues()

        self.opened = True

    def close(self):
        """Open the joystick device"""
        if not self.opened:
            return

        self.jsfile.close()
        self.opened = False

    def __initvalues(self):
        """Read the buttons and axes initial values from the js device"""
        for _ in range(len(self.axes) + len(self.buttons)):
            data = self.jsfile.read(struct.calcsize(JS_EVENT_FMT))
            jsdata = struct.unpack(JS_EVENT_FMT, data)
            self.__updatestate(jsdata)

    def __updatestate(self, jsdata):
        """Update the internal absolute state of buttons and axes"""
        if jsdata[JE_TYPE] & JS_EVENT_AXIS != 0:
            self.axes[jsdata[JE_NUMBER]] = jsdata[JE_VALUE] / 32768.0
        elif jsdata[JE_TYPE] & JS_EVENT_BUTTON != 0:
            self.buttons[jsdata[JE_NUMBER]] = jsdata[JE_VALUE]

    def __decode_event(self, jsdata):
        """ Decode a jsdev event into a dict """
        #TODO: Add timestamp?
        if jsdata[JE_TYPE] & JS_EVENT_AXIS != 0:
            return JEvent(evt_type=TYPE_AXIS,
                          number=jsdata[JE_NUMBER],
                          value=jsdata[JE_VALUE] / 32768.0)
        if jsdata[JE_TYPE] & JS_EVENT_BUTTON != 0:
            return JEvent(evt_type=TYPE_BUTTON,
                          number=jsdata[JE_NUMBER],
                          value=jsdata[JE_VALUE] / 32768.0)

    def _read_all_events(self):
        """Consume all the events queued up in the JS device"""
        try:
            while True:
                data = self.jsfile.read(struct.calcsize(JS_EVENT_FMT))
                jsdata = struct.unpack(JS_EVENT_FMT, data)
                self.__updatestate(jsdata)
        except IOError:  # Raised when there are nothing to read
            pass

    def read(self):
        """ Returns a list of all joystick event since the last call """
        if not self.opened:
            raise Exception("Joystick device not opened")

        self._read_all_events()

        return [self.axes, self.buttons]
