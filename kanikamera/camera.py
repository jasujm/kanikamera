"""Camera services

This module contains manager classes for capturing still images and video in
response to events. The exposed interface is pyev watchers that can be attached
to event loop.
"""

from datetime import datetime
from io import BytesIO
import logging
import subprocess
from tempfile import TemporaryFile, NamedTemporaryFile
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

    def capture_with_camera(self, callback):
        """Capture image with camera

        Args:
            callback: Callback for capturing image with initialized camera. The
                PiCamera object is passed as parameter to the callback.
        """
        now = localtime()
        if now.tm_hour < 8 or now.tm_hour >= 17 or now.tm_wday >= 5:
            logging.debug("Time not between 8 and 17, not capturing")
            return None

        try:
            with PiCamera(**self._camera_config) as camera:
                callback(camera)
        except PiCameraError as e:
            logging.warn("PiCamera error: %r", e)

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
        self.capture_with_camera(self._capture_still_image)

    def _capture_still_image(self, camera):
        logging.debug("Capturing still image, config: %r", self._camera_config)
        with BytesIO() as img:
            camera.capture(img, format="jpeg")
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
                logging.debug("Capturing video: %r", self._camera_config)
                self.capture_with_camera(self._capture_video)
            self._last_motion_time = motion_time

    def _capture_video(self, camera):
        # TODO: Pipes would work better than temporary files here
        # Optimally data could be streamed to avconv while still
        # being captured
        with TemporaryFile() as tmpcam, NamedTemporaryFile() as tmpdbx:
            camera.start_recording(tmpcam, format="h264")
            camera.wait_recording(self._video_duration)
            camera.stop_recording()
            args = ["avconv", "-y", "-r", str(camera.framerate),
                    "-i", "pipe:0", "-f", "mp4", tmpdbx.name]
            logging.debug("Calling avconv with args: %r", args)
            tmpcam.seek(0)
            p = subprocess.Popen(args, stdin=tmpcam, stderr=subprocess.PIPE)
            _, err = p.communicate()
            if p.returncode == 0:
                tmpdbx.seek(0)
                self.upload_image("mp4", tmpdbx.read())
            else:
                logging.warn("Converting video failed: %r", err)
