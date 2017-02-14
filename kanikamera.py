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
    return config


def capture_and_upload(token, resolution):
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
    token = config["Dropbox"]["Token"]
    resolution = config.get("Kanikamera", "Resolution", fallback="2592x1944")
    resolution = tuple(int(x.strip()) for x in resolution.split("x"))
    while True:
        capture_and_upload(token, resolution)
        time.sleep(300)


if __name__ == '__main__':
    main()
