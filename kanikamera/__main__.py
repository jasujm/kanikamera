from argparse import ArgumentParser
from configparser import ConfigParser
from contextlib import suppress
from datetime import datetime
from io import BytesIO
import logging
import os
import signal
import sys

from dropbox import Dropbox
from dropbox.exceptions import DropboxException
from picamera import PiCamera, PiCameraError
import pyev
import systemd.journal
import xdg

from kanikamera.motionsensor import MotionSensor


def parse_args():
    parser = ArgumentParser(description="Kanimakera service")
    parser.add_argument("-v", "--verbose", action="count", help="verbose logging")
    return parser.parse_args(sys.argv[1:])


def init_logging(args):
    sys.argv[0] = os.path.basename(sys.argv[0])
    if args.verbose and args.verbose > 0:
        level = logging.INFO
        if args.verbose > 1:
            level = logging.DEBUG
        logging.basicConfig(level=level)
    logging.root.addHandler(systemd.journal.JournalHandler())


def get_config():
    config = ConfigParser()
    paths = [xdg.XDG_CONFIG_HOME] + xdg.XDG_CONFIG_DIRS
    config.read(os.path.join(path, "kanikamera") for path in reversed(paths))
    return config


def init_config_dict(config, key):
    if key in config:
        return dict(**config[key])
    return {}


def capture_and_upload(watcher, revents):
    token, camera_config = watcher.data
    imgfile = BytesIO()
    logging.debug("Capturing still image, config: %r", camera_config)
    try:
        with PiCamera(**camera_config) as camera:
            camera.capture(imgfile, format="jpeg")
    except PiCameraError as e:
        logging.warn("PiCamera error: %r", e)
    now = datetime.now()
    upload_file = "/Kanikuvat/{}/{}.jpg".format(
        now.strftime("%Y%m%d"), now.strftime("%H%M%S"))
    logging.debug("Uploading image to Dropbox, file: %r", upload_file)
    try:
        dropbox = Dropbox(token)
        dropbox.files_upload(imgfile.getvalue(), upload_file)
    except DropboxException as e:
        logging.warn("Dropbox error: %r", e)


def motion_detected(watcher, revents):
    logging.debug("Motion detected: %r", watcher.data)


def terminate(watcher, revents):
    logging.debug("Terminate signal received")
    watcher.loop.stop()


def main():
    args = parse_args()
    init_logging(args)

    config = get_config()
    try:
        token = config["Dropbox"]["token"]
    except KeyError:
        logging.fatal("Dropbox authentication token not found. Exiting.")
        sys.exit(1)
    camera_config = init_config_dict(config, "Camera")
    timer_config = init_config_dict(config, "Timer")
    interval = float(timer_config.pop("interval", 300))
    motion_sensor_config = init_config_dict(config, "MotionSensor")

    loop = pyev.default_loop()
    timer = loop.timer(0, interval, capture_and_upload, (token, camera_config))
    timer.start()
    sig = loop.signal(signal.SIGTERM, terminate)
    sig.start()
    motion = loop.async(motion_detected)
    motion.start()

    with MotionSensor(motion_sensor_config, motion):
        loop.start()

if __name__ == '__main__':
    main()
