from configparser import ConfigParser
from datetime import datetime
from io import BytesIO
import os
import time

from dropbox import Dropbox
from picamera import PiCamera

def capture_and_upload(token):
    imgfile = BytesIO()
    with PiCamera(sensor_mode=3, resolution=(2592,1944)) as camera:
        camera.capture(imgfile, format="jpeg", resize=(800,600))
    upload_file = "/Kanikuvat/{}.jpg".format(datetime.now().strftime("%Y%m%d-%H%M%S"))
    dropbox=Dropbox(token)
    dropbox.files_upload(imgfile.getvalue(), upload_file)

def main():
    config = ConfigParser()
    config.read(os.path.expanduser("~/.kanikamera"))
    token = config.get("Dropbox", "Token")
    while True:
        capture_and_upload(token)
        time.sleep(300)

if __name__ == '__main__':
    main()
