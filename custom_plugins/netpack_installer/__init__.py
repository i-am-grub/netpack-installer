import io
import logging
import sys
from pathlib import Path
from zipfile import ZipFile

import esptool
import gevent.lock
import gevent.subprocess
import requests
from RHUI import UIField, UIFieldSelectOption, UIFieldType

logger = logging.getLogger(__name__)
_lock = gevent.lock.BoundedSemaphore()


class NetpackInstaller:

    def __init__(self, rhapi) -> None:
        self._rhapi = rhapi
        self._firmware_folder = Path(rhapi.server.data_dir).joinpath(
            "plugins/netpack_installer/firmware"
        )
        self._downloaded = False

    def _download_firmware(self) -> None:

        session = requests.Session()

        lat_green = gevent.spawn(
            session.get,
            "https://api.github.com/repos/i-am-grub/elrs-netpack/releases/latest",
        )
        gevent.wait((lat_green,))
        latest_data = lat_green.value.json()

        message = f"Downloading firmware version {latest_data['tag_name']}"
        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

        data_green = gevent.spawn(
            session.get, latest_data["assets"][0]["browser_download_url"]
        )
        gevent.wait((data_green,))

        with ZipFile(io.BytesIO(data_green.value.content)) as zip_:
            zip_.extractall(self._firmware_folder)

        self._downloaded = True

    def flash_firmware(self, *_) -> None:
        if _lock.locked():
            message = "Flashing already in progress"
            self._rhapi.ui.message_notify(self._rhapi.language.__(message))
            return

        with _lock:

            if not self._downloaded:
                self._download_firmware()

            if not (port := self._rhapi.db.option("_netpack_ports")):
                message = "Port not selected"
                self._rhapi.ui.message_notify(self._rhapi.language.__(message))
                return

            boot = self._firmware_folder.joinpath("bootloader.bin")
            firm = self._firmware_folder.joinpath("elrs-netpack.bin")
            part = self._firmware_folder.joinpath("partition-table.bin")

            message = "Flashing firmware"
            self._rhapi.ui.message_notify(self._rhapi.language.__(message))

            process = gevent.subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "esptool",
                    "-p",
                    port,
                    "-b",
                    "460800",
                    "--before",
                    "default_reset",
                    "--after",
                    "hard_reset",
                    "--chip",
                    "esp32s3",
                    "write_flash",
                    "--flash_mode",
                    "dio",
                    "--flash_freq",
                    "80m",
                    "--flash_size",
                    "2MB",
                    "0x0",
                    str(boot.absolute()),
                    "0x10000",
                    str(firm.absolute()),
                    "0x8000",
                    str(part.absolute()),
                ],
            )

            try:
                process.check_returncode()
            except gevent.subprocess.CalledProcessError:
                message = "Netpack flashing failed"
                self._rhapi.ui.message_notify(self._rhapi.language.__(message))
                logger.error(process.stdout)
            else:
                message = "Netpack flashing completed"
                self._rhapi.ui.message_notify(self._rhapi.language.__(message))

    def update_port_list(self, *_):

        _netpack_ports = UIField(
            "_netpack_ports",
            "Netpack Serial Port",
            desc="The serial port the netpack is connected to",
            field_type=UIFieldType.SELECT,
            options=[
                UIFieldSelectOption(value=port, label=port)
                for port in esptool.get_port_list()
            ],
        )
        self._rhapi.fields.register_option(_netpack_ports, "netpack_panel")
        self._rhapi.ui.broadcast_ui("settings")


def initialize(rhapi):

    rhapi.ui.register_panel(
        "netpack_panel", "ELRS Netpack Firmware", "settings", order=0
    )

    installer = NetpackInstaller(rhapi)
    installer.update_port_list()

    rhapi.ui.register_quickbutton(
        "netpack_panel",
        "update_netpack_ports",
        "Refresh Ports",
        installer.update_port_list,
    )

    rhapi.ui.register_quickbutton(
        "netpack_panel",
        "flash_netpack_",
        "Flash Netpack Firmware",
        installer.flash_firmware,
    )
