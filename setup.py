from setuptools import setup

setup(
    name="Kanikamera",
    py_modules="kanikamera",
    entry_points={
        "console_scripts" : [
            "kanikamera = kanikamera:main"
        ]
    },
    install_requires=[
        "dropbox>=7.1", "picamera>=1.12", "xdg>=1.0", "systemd-python"
    ]
)
