"""The motion sensor services"""

import logging

import RPi.GPIO as GPIO

class MotionSensor:
    """Class for controlling motion sensor

    The class exports the necessary GPIO reserved for the sensor and is
    responsible for generating events when the sensor detects motion.

    This class defines context manager and can be used in with statement
    ensuring that :func:`cleanup` is called.
    """

    def __init__(self, config, watcher):
        """Initialize motion sensor

        Initializing sets up the necessary GPIO and starts waiting for events.

        Args:
            config: The MotionSensor section of the configuration file
            watcher: The async watcher used to notify about motion. Watcher data
                will be a boolean indicating the motion status.
        """
        if "gpio" in config:
            self.gpio = int(config["gpio"])
            self._watcher = watcher
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio, GPIO.IN)
            GPIO.add_event_detect(self.gpio, GPIO.RISING)
            GPIO.add_event_callback(self.gpio, self._motion_detect_event)
        else:
            self.gpio = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()

    def cleanup(self):
        """Perform cleanup

        This method cleans the motion sensor GPIO."""
        if self.gpio:
            GPIO.cleanup(self.gpio)

    def _motion_detect_event(self, gpio):
        # Ideally we would like to detect the motion by polling POLLPRI on the
        # GPIO file descriptor, making the additional event thread spawned by
        # the RPi.GPIO library unnecessary. pyev does not support that so before
        # rolling up a proper event library that support POLLPRI, async
        # notifications suffice.
        self._watcher.data = bool(GPIO.input(gpio))
        self._watcher.send()
