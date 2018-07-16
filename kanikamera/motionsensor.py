"""The motion sensor services"""

import asyncio
import logging

import RPi.GPIO as GPIO


class MotionSensor:
    """Class for controlling motion sensor

    The class exports the necessary GPIO reserved for the sensor and is
    responsible for generating events when the sensor detects motion.

    Motion detection runs in a separate thread allocated by the
    :class:`RPi.GPIO` library. The interface this class provides for the event
    loop is an event object.

    This class defines context manager and can be used in with statement
    ensuring that :func:`close` is called.

    """

    def __init__(self, config, loop):
        """Initialize motion sensor

        Initializing sets up the necessary GPIO and starts waiting for events.

        Args:
            config: The MotionSensor section of the configuration file
            loop: The event loop
        """
        if "gpio" in config:
            self.gpio = int(config["gpio"])
            self._loop = loop
            self._motion_detect_event = asyncio.Event(loop=loop)
            self._motion_stop_event = asyncio.Event(loop=loop)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio, GPIO.IN)
            GPIO.add_event_detect(self.gpio, GPIO.RISING)
            GPIO.add_event_callback(self.gpio, self._handle_motion_detected)
        else:
            self.gpio = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        """Perform cleanup

        This method cleans up the motion sensor GPIO."""
        if self.gpio:
            GPIO.cleanup(self.gpio)

    @property
    def motion_detect_event(self):
        """Event that signals when motion is detected

        Return:
            An :class:`asyncio.Event` object which is set when motion is
            detected and cleared when motion is no longer detected.
        """
        return self._motion_detect_event

    @property
    def motion_stop_event(self):
        """Event that signals when motion is stopped

        Return:
            An :class:`asyncio.Event` object which is set when motion is
            stopped and cleared when motion is again detected.
        """
        return self._motion_stop_event

    def _handle_motion_detected(self, gpio):
        # Ideally we would like to detect the motion by polling POLLPRI on the
        # GPIO file descriptor, making the additional event thread spawned by
        # the RPi.GPIO library unnecessary. asyncio does not support POLLPRI,
        # however.
        if GPIO.input(gpio):
            self._loop.call_soon_threadsafe(self._motion_detect_event.set)
            self._loop.call_soon_threadsafe(self._motion_stop_event.clear)
        else:
            self._loop.call_soon_threadsafe(self._motion_detect_event.clear)
            self._loop.call_soon_threadsafe(self._motion_stop_event.set)
