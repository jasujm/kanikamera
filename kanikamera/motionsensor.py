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

    def __init__(self, config):
        """Initialize motion sensor

        Initializing sets up the necessary GPIO and starts waiting for events.

        Args:
            config: The MotionSensor section of the configuration file
        """
        if "gpio" in config:
            self.gpio = int(config["gpio"])
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
        logging.debug("Motion {}".format(GPIO.input(gpio)))
