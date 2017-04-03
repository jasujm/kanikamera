# Kanikamera

Kanikamera (“the bunny camera”) is a small project I use to spy my pet cats
during the day when I’m not home. It uses the Raspberry Pi camera to take still
images every now and then and uploads them to Dropbox using
the [Dropbox API](https://www.dropbox.com/developers). It even supports plugging
motion sensor to Raspberry Pi GPIOs to take a short video whenever it detects
the little ones entering the room.

The program is for very special purpose and not very configurable. However, it’s
small enough for doing some hacking.

## Installing

I run the program as systemd service which I start before I leave for work and
stop when I come back. The unit file is very simple

    [Unit]
    Description=Kanikamera

    [Install]
    WantedBy=multi-user.target

    [Service]
    ExecStart=/path/to/kanikamera
    User=<user>
    StandardOutput=null
    StandardError=null

## Configuration

The configurations are stored in a single configuration file called `kanikamera`
that is searched from paths according
to
[XDG Base Directory Specification](https://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html).
For example, the config file could be located in
`/home/<user>/.config/kanikamera`.

At the very least the program needs to know access token for the Dropbox app
where the images and videos are uploaded.

A sample config file could be like this:

    [Dropbox]
    token=<Dropbox token>

    [Camera]
    resolution=800x600

    [StillImage]
    interval=300

    [Video]
    motionless_period=1800
    video_duration=60

    [MotionSensor]
    gpio=7
