from setuptools import setup

setup(
    name="Kanikamera",
    packages=[
        "kanikamera",
    ],
    entry_points={
        "console_scripts" : [
            "kanikamera=kanikamera.__main__:main",
        ],
    },
    install_requires=[
        "dropbox>=7.1",
        "picamera>=1.12",
        "xdg>=1.0",
        "systemd-python",
        "pyev>=0.9",
    ],
)
