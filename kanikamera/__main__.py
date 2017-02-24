from configparser import ConfigParser
from contextlib import suppress
from datetime import datetime
from io import BytesIO
import logging
import os
import sys
import time

from dropbox import Dropbox
from dropbox.exceptions import DropboxException
from picamera import PiCamera, PiCameraError
import systemd.journal
import xdg


def init_logging():
    sys.argv[0] = os.path.basename(sys.argv[0])
    logging.root.addHandler(systemd.journal.JournalHandler())


def get_config():
    config = ConfigParser()
    paths = [xdg.XDG_CONFIG_HOME] + xdg.XDG_CONFIG_DIRS
    config.read(os.path.join(path, "kanikamera") for path in reversed(paths))

    try:
        ret = { "token": config["Dropbox"]["Token"] }
    except KeyError:
        logging.fatal("Dropbox authentication token not found. Exiting.")
        sys.exit(1)

    if "Kanikamera" in config:
        kanikamera = config["Kanikamera"]
        with suppress(KeyError):
            ret["resolution"] = kanikamera["Resolution"]
        with suppress(KeyError):
            ret["interval"] = float(kanikamera["Interval"])
    return ret


def capture_and_upload(token, camera_config):
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
    token = config.pop("token")
    interval = config.pop("interval", 300)
    while True:
        tic = time.monotonic()
        capture_and_upload(token, config)
        time.sleep(max(interval + tic - time.monotonic(), 0))


if __name__ == '__main__':
    main()