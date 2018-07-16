"""The motion sensor services"""

import asyncio
import logging

import RPi.GPIO as GPIO


class MotionSensor:
    """Class for controlling motion sensor

    The class exports the necessary GPIO reserved for the sensor and is
    responsible for generating events when the sensor detects motion.

    This class defines context manager and can be used in with statement
    ensuring that :func:`close` is called.
    """

    def __init__(self, config, loop, coroutine):
        """Initialize motion sensor

        Initializing sets up the necessary GPIO and starts waiting for events.

        Args:
            config: The MotionSensor section of the configuration file
            loop: The event loop
            coroutine: The coroutine function to generate coroutine to be
                scheduled on motion event
        """
        if "gpio" in config:
            self.gpio = int(config["gpio"])
            self._loop = loop
            self._coroutine = coroutine
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio, GPIO.IN)
            GPIO.add_event_detect(self.gpio, GPIO.RISING)
            GPIO.add_event_callback(self.gpio, self._motion_detect_event)
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

    def _motion_detect_event(self, gpio):
        # Ideally we would like to detect the motion by polling POLLPRI on the
        # GPIO file descriptor, making the additional event thread spawned by
        # the RPi.GPIO library unnecessary. asyncio does not support POLLPRI,
        # however.
        is_motion = bool(GPIO.input(gpio))
        event_time = self._loop.time()
        coro = self._coroutine(is_motion, event_time)
        asyncio.run_coroutine_threadsafe(coro, self._loop)
