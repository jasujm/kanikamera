from contextlib import suppress
from datetime import datetime
from io import BytesIO
import logging
import os
import time

from dropbox import Dropbox
from dropbox.exceptions import DropboxException
from picamera import PiCamera, PiCameraError


def get_config():
    import configparser
    import xdg

    config = configparser.ConfigParser()
    paths = [xdg.XDG_CONFIG_HOME] + xdg.XDG_CONFIG_DIRS
    config.read(os.path.join(path, "kanikamera") for path in reversed(paths))

    ret = { "token": config["Dropbox"]["Token"] }
    if "Kanikamera" in config:
        kanikamera = config["Kanikamera"]
        with suppress(KeyError):
            ret["resolution"] = kanikamera["Resolution"]
        with suppress(KeyError):
            ret["interval"] = float(kanikamera["Interval"])
    return ret


def capture_and_upload(token, resolution=(2592,1944)):
    imgfile = BytesIO()
    try:
        with PiCamera(resolution=resolution) as camera:
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
    config = get_config()
    interval = config.pop("interval", 300)
    while True:
        tic = time.monotonic()
        capture_and_upload(**config)
        time.sleep(max(interval + tic - time.monotonic(), 0))


if __name__ == '__main__':
    main()
