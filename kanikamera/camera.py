"""Camera services

This module contains manager classes for capturing still images and video in
response to events. The exposed interface is pyev watchers that can be attached
to event loop.
"""

from datetime import datetime
from io import BytesIO
import logging

from dropbox import Dropbox
from dropbox.exceptions import DropboxException
from picamera import PiCamera, PiCameraError


class ImageManagerBase:
    """Base class for image manager

    Offers image capture and upload as services for the derived classes.
    """

    def __init__(self, token, camera_config):
        """Initialize image manager base

        Args:
            token: Dropbox token for uploading images
            camera_config: dictionary of configuration values for the camera
                module
        """
        self._token = token
        self._camera_config = camera_config

    def capture_with_camera(self, callback):
        """Capture image with camera

        Args:
            callback: Callback for capturing image with initialized camera. The
                callback gets a PiCamera object and file the image is written
                to.
        """
        img = BytesIO()
        try:
            with PiCamera(**self._camera_config) as camera:
                callback(camera, img)
        except PiCameraError as e:
            logging.warn("PiCamera error: %r", e)
        return img

    def upload_image(self, format, img):
        """Upload image to Dropbox

        Args:
            format: file extension for the uploaded file
            img: the contents (bytes) of the image
        """
        now = datetime.now()
        upload_file = "/Kanikuvat/{}/{}.{}".format(
            now.strftime("%Y%m%d"), now.strftime("%H%M%S"), format)
        logging.debug("Uploading image to Dropbox, file: %r", upload_file)
        try:
            dropbox = Dropbox(self._token)
            dropbox.files_upload(img.getvalue(), upload_file)
        except DropboxException as e:
            logging.warn("Dropbox error: %r", e)


class StillImageManager(ImageManagerBase):
    """Manager of still images

    Still images are taken in regular intervals.
    """

    def __init__(self, token, camera_config, interval):
        """Initialize the manager

        Args:
            token: Dropbox token for uploading images
            camera_config: dictionary of configuration values for the camera
                module
            interval: the capture interval in seconds
        """
        super(StillImageManager, self).__init__(token, camera_config)
        self._interval = interval

    def get_watcher(self, loop):
        """Get watcher that can be registered to event loop"""
        return loop.timer(0, self._interval, self._capture_and_upload)

    def _capture_and_upload(self, watcher, revents):
        def capture_still_image(camera, img):
            camera.capture(img, format="jpeg")
        logging.debug("Capturing still image, config: %r", self._camera_config)
        img = self.capture_with_camera(capture_still_image)
        self.upload_image("jpg", img)
