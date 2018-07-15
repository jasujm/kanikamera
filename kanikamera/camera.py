"""Camera services

This module contains manager classes for capturing still images and video in
response to events. The exposed interface is coroutines that can be attached to
event loop.
"""

import asyncio
from contextlib import ExitStack
from datetime import datetime
from io import BytesIO
import logging
import os
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

    def capture_with_camera(self, callback):
        """Capture image with camera

        Args:
            callback: Callback for capturing image with initialized camera. The
                PiCamera object is passed as parameter to the callback.
        """
        now = localtime()
        if now.tm_hour < 9 or now.tm_hour >= 17 or now.tm_wday >= 5:
            logging.debug("Time not between 9 and 17, not capturing")
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

    async def __call__(self):
        """Generate coroutine that takes periodic photos when attached to event loop"""
        while True:
            logging.debug("Capturing still image, config: %r", self._camera_config)
            self.capture_with_camera(self._capture_still_image)
            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    def _capture_still_image(self, camera):
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

    async def __call__(self, is_motion, event_time):
        """Generate coroutine that captures video when motion is detected

        Args:
            is_motion: True if motion was detected, False if detection stopped
            event_time: Timestamp of the event

        Todo:
            It's not very coroutin-y because it blocks for capturing video,
            converting and uploading. And it doesn't actually detect motion
            either but depends on external object to schedule it with event
            data. In the future it could be refactored to usefully to monitor
            motion itself using semaphores, condition variables etc. as
            mechanism, and yield back to event loop in useful manner.
        """
        self._motion_detected(is_motion, event_time)

    def _motion_detected(self, is_motion, event_time):
        logging.debug("Motion detected: %r, Time: %r", is_motion, event_time)
        if is_motion:
            logging.debug(
                "Motion was detected, last: {}, now: {}".format(
                    self._last_motion_time, event_time))
            if (not self._last_motion_time or
                event_time - self._last_motion_time > self._motionless_period):
                logging.debug("Capturing video: %r", self._camera_config)
                self.capture_with_camera(self._capture_video)
            self._last_motion_time = event_time

    def _capture_video(self, camera):
        with NamedTemporaryFile() as tmpdbx, ExitStack() as s1, ExitStack() as s2:
            r, w = os.pipe2(os.O_CLOEXEC)
            s1.callback(lambda: os.close(w))
            s2.callback(lambda: os.close(r))
            args = ["avconv", "-y", "-r", str(camera.framerate),
                    "-i", "pipe:0", "-f", "mp4", tmpdbx.name]
            logging.debug("Calling avconv with args: %r", args)
            p = subprocess.Popen(args, stdin=r, stderr=subprocess.PIPE)
            s2.close()
            camera.start_recording(
                open(w, 'bw', buffering=0, closefd=False), format="h264")
            camera.wait_recording(self._video_duration)
            camera.stop_recording()
            s1.close()
            _, err = p.communicate()
            if p.returncode == 0:
                tmpdbx.seek(0)
                self.upload_image("mp4", tmpdbx.read())
            else:
                logging.warn("Converting video failed: %r", err)
