"""Camera services

This module contains manager classes for capturing still images and video in
response to events. The exposed interface is pyev watchers that can be attached
to event loop.
"""

from datetime import datetime
from io import BytesIO
import logging
import subprocess
from tempfile import NamedTemporaryFile
from time import localtime

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
        self._framerate = None

    def capture_with_camera(self, callback):
        """Capture image with camera

        Args:
            callback: Callback for capturing image with initialized camera. The
                callback gets a PiCamera object and file the image is written
                to.
        """
        now = localtime()
        if now.tm_hour < 8 or now.tm_hour >= 17 or now.tm_wday >= 5:
            logging.debug("Time not between 8 and 17, not capturing")
            return None

        img = BytesIO()
        try:
            with PiCamera(**self._camera_config) as camera:
                self._framerate = camera.framerate
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
            dropbox.files_upload(img, upload_file)
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
        if img:
            self.upload_image("jpg", img.getvalue())


class VideoManager(ImageManagerBase):
    """Manager of video capture

    Video is captured when motion is detected, if there hasn't been any motion
    in a while as defined by an user supplied parameter."""

    def __init__(self, token, camera_config, motionless_period, video_duration):
        """Initialize the manager

        Args:
            token: Dropbox token for uploading images
            camera_config: dictionary of configuration values for the camera
                module
            motionless_period: period in second that there must be no motion in
                order for video capture to start
            video_duration: the duration of the captured video in seconds
        """
        super(VideoManager, self).__init__(token, camera_config)
        self._motionless_period = motionless_period
        self._video_duration = video_duration
        self._last_motion_time = None

    def get_watcher(self, loop):
        """Get watcher that can be registered to event loop

        The watcher is an py:class:`pyev.Async` instance. In order to handle a
        motion event, the watched data must be set as a tuple containing bool
        indicating whether motion has been detected and monotonic time of the
        event.
        """
        return loop.async(self._motion_detected)

    def _motion_detected(self, watcher, revents):
        logging.debug("Motion detected: %r", watcher.data)
        is_motion, motion_time = watcher.data
        if is_motion:
            logging.debug(
                "Motion was detected, last: {}, now: {}".format(
                    self._last_motion_time, motion_time))
            if (not self._last_motion_time or
                motion_time - self._last_motion_time > self._motionless_period):
                logging.debug("Capturing video")
                img = self.capture_with_camera(self._capture_video)
                if img:
                    # TODO: Pipes would work better than temporary files here
                    # Optimally data could be streamed to avconv while still
                    # being captured
                    with NamedTemporaryFile(suffix=".h264") as tmpcam, \
                         NamedTemporaryFile(suffix=".mp4") as tmpdbx:
                        tmpcam.write(img.getvalue())
                        args = ["avconv", "-y", "-r", str(self._framerate),
                                "-i", tmpcam.name, tmpdbx.name]
                        logging.debug("Calling avconv with args: %r", args)
                        result = subprocess.call(
                            args, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
                        if res == 0:
                            tmpdbx.seek(0)
                            self.upload_image("mp4", tmpdbx.read())
                        else:
                            logging.warn("Converting video failed: %r", result)
            self._last_motion_time = motion_time

    def _capture_video(self, camera, img):
        camera.start_recording(img, format="h264")
        camera.wait_recording(self._video_duration)
        camera.stop_recording()
