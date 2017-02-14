from contextlib import suppress
from datetime import datetime
from io import BytesIO
import os
import time

from dropbox import Dropbox
from picamera import PiCamera


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
            ret["resolution"] = tuple(
                int(x.strip()) for x in kanikamera["Resolution"].split("x"))
    return ret


def capture_and_upload(token, resolution=(2592,1944)):
    imgfile = BytesIO()
    with PiCamera(resolution=resolution) as camera:
        camera.capture(imgfile, format="jpeg")
    now = datetime.now()
    upload_file = "/Kanikuvat/{}/{}.jpg".format(
        now.strftime("%Y%m%d"), now.strftime("%H%M%S"))
    dropbox = Dropbox(token)
    dropbox.files_upload(imgfile.getvalue(), upload_file)


def main():
    config = get_config()
    while True:
        capture_and_upload(**config)
        time.sleep(300)


if __name__ == '__main__':
    main()
