"""Camera services

This module contains manager classes for capturing still images and video in
response to events. The exposed interface is coroutines that can be attached to
event loop.

Todo:
    Do not block in the event loop when capturing/converting/uploading
    images/videos.
"""

import asyncio
import contextlib
from datetime import datetime
import functools
from io import BytesIO
import logging
import subprocess
from tempfile import NamedTemporaryFile
from time import localtime

from dropbox import Dropbox
from dropbox.exceptions import DropboxException
from picamera import PiCamera, PiCameraError
from requests.exceptions import RequestException


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
        self._camera_lock = asyncio.Lock()

    async def capture_with_camera(self, coro):
        """Capture image with camera

        Image is only captured during office hours (Mon-Fri 9-17). The actual
        capturing is delegated to a callback that gets camera resource as its
        argument.

        Args:
            coro: Coroutine function for capturing image with camera. The
               PiCamera object is passed as an argument to the generator. While
               awaiting for the generator, a lock is held to prevent any other
               callback accessing the camera hardware.
        """
        now = localtime()
        if now.tm_hour < 9 or now.tm_hour >= 17 or now.tm_wday >= 5:
            logging.debug(
                "Requested to capture image/video using %r but it's not office hours",
                coro)
            return

        try:
            async with self._camera_lock:
                with PiCamera(**self._camera_config) as camera:
                    await coro(camera)
        except PiCameraError:
            logging.exception("PiCamera failure")

    async def upload_image(self, format, img):
        """Upload image to Dropbox

        Args:
            format: file extension for the uploaded file
            img: the contents (bytes) of the image
        """
        now = datetime.now()
        upload_file = "/Kanikuvat/{}/{}.{}".format(
            now.strftime("%Y%m%d"), now.strftime("%H%M%S"), format)
        def do_upload_image():
            logging.debug("Uploading image to Dropbox, file: %r", upload_file)
            try:
                dropbox = Dropbox(self._token)
                dropbox.files_upload(img, upload_file)
            except (DropboxException, RequestException):
                logging.exception("Dropbox failure")
        await asyncio.get_event_loop().run_in_executor(None, do_upload_image)


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
        with contextlib.suppress(asyncio.CancelledError):
            while not asyncio.Task.current_task().cancelled():
                await self.capture_with_camera(self._capture_still_image)
                await asyncio.sleep(self._interval)

    async def _capture_still_image(self, camera):
        logging.debug("Capturing still image, config: %r", self._camera_config)
        with BytesIO() as img:
            await asyncio.get_event_loop().run_in_executor(
                None, functools.partial(camera.capture, img, format="jpeg"))
            await self.upload_image("jpg", img.getvalue())


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

    async def __call__(self, motion_detect_event, motion_stop_event):
        """Generate coroutine that captures video when motion is detected

        Args:
            motion_detect_event: awaitable event for signaling motion detected
            motion_stop_event: awaitable event for signaling motion stopped
        """
        with contextlib.suppress(asyncio.CancelledError):
            while not asyncio.Task.current_task().cancelled():
                logging.debug("Waiting to detect motion")
                await motion_detect_event.wait()
                await self._handle_motion_detected()
                await motion_stop_event.wait()

    async def _handle_motion_detected(self):
        motion_time = asyncio.get_event_loop().time()
        logging.debug(
            "Motion detected at %r. Last was: %r",
            motion_time, self._last_motion_time)
        if (not self._last_motion_time or
            motion_time - self._last_motion_time > self._motionless_period):
            await self.capture_with_camera(self._capture_video)
        self._last_motion_time = motion_time

    def _record_video(self, camera, f):
        camera.start_recording(f, format="h264")
        camera.wait_recording(self._video_duration)
        camera.stop_recording()

    async def _capture_video(self, camera):
        logging.debug("Capturing video, config: %r", self._camera_config)
        loop = asyncio.get_event_loop()
        with NamedTemporaryFile() as tmpdbx:
            # This might be considered abusing the synchronous subprocess API in
            # asynchronous code. The asyncio subprocess API makes it tedious to
            # write to the pipe feeding avconv its input from the thread running
            # the camera.
            args = ["avconv", "-y", "-r", str(camera.framerate),
                    "-i", "pipe:0", "-f", "mp4", tmpdbx.name]
            logging.debug("Calling avconv with args: %r", args)
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            await loop.run_in_executor(None, self._record_video, camera, p.stdin)
            _, err = await loop.run_in_executor(None, p.communicate)
            if p.returncode == 0:
                tmpdbx.seek(0)
                await self.upload_image("mp4", tmpdbx.read())
            else:
                logging.warn("Converting video failed: %r", err)
