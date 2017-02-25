from configparser import ConfigParser
from contextlib import suppress
from datetime import datetime
from io import BytesIO
import logging
import os
import sys

from dropbox import Dropbox
from dropbox.exceptions import DropboxException
from picamera import PiCamera, PiCameraError
import pyev
import systemd.journal
import xdg


def init_logging():
    sys.argv[0] = os.path.basename(sys.argv[0])
    logging.root.addHandler(systemd.journal.JournalHandler())


def get_config():
    config = ConfigParser()
    paths = [xdg.XDG_CONFIG_HOME] + xdg.XDG_CONFIG_DIRS
    config.read(os.path.join(path, "kanikamera") for path in reversed(paths))
    return config


def capture_and_upload(watcher, revents):
    token, camera_config = watcher.data
    imgfile = BytesIO()
    try:
        with PiCamera(**camera_config) as camera:
            camera.capture(imgfile, format="jpeg")
    except PiCameraError as e:
        logging.warn("PiCamera error: %r", e)
    now = datetime.now()
    upload_file = "/Kanikuvat/{}/{}.jpg".format(
        now.strftime("%Y%m%d"), now.strftime("%H%M%S"))
    try:
        dropbox = Dropbox(token)
        dropbox.files_upload(imgfile.getvalue(), upload_file)
    except DropboxException as e:
        logging.warn("Dropbox error: %r", e)


def main():
    init_logging()

    config = get_config()
    try:
        token = config["Dropbox"]["token"]
    except KeyError:
        logging.fatal("Dropbox authentication token not found. Exiting.")
        sys.exit(1)
    camera_config = config["Camera"] if "Camera" in config else {}
    timer_config = config["Timer"] if "Timer" in config else {}
    interval = float(timer_config.pop("interval", 300))

    loop = pyev.default_loop()
    timer = loop.timer(0, interval, capture_and_upload, (token, camera_config))
    timer.start()
    loop.start()


if __name__ == '__main__':
    main()
