import io
import logging
import sys
from pathlib import Path
from zipfile import ZipFile

import esptool
import gevent.lock
import gevent.subprocess
import requests
from eventmanager import Evt
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
        self.session = requests.Session()

        ver_green = gevent.spawn(
            self._get_download_versions,
        )
        gevent.wait((ver_green,))
        self._versions = ver_green.value

        self.update_version_list()

    def _get_download_versions(self) -> list:

        try:
            data = self.session.get(
                "https://api.github.com/repos/i-am-grub/elrs-netpack/releases",
                timeout=5,
            )
        except Exception:
            return []

        return data.json()

    def _download_firmware(self) -> None:

        url = self._rhapi.db.option("_netpack_version")
        if url is None:
            message = "Firmware version not selected"
            self._rhapi.ui.message_notify(self._rhapi.language.__(message))
            return

        message = "Downloading firmware"
        self._rhapi.ui.message_notify(self._rhapi.language.__(message))

        data_green = gevent.spawn(self.session.get, url)
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
            "Serial Port",
            desc="The serial port the netpack is connected to for flashing fimrware",
            field_type=UIFieldType.SELECT,
            options=[
                UIFieldSelectOption(value=port, label=port)
                for port in esptool.get_port_list()
            ],
        )
        self._rhapi.fields.register_option(_netpack_ports, "netpack_panel")
        self._rhapi.ui.broadcast_ui("settings")

    def update_version_list(self, args=None):

        def generate_options():
            allow_beta = self._rhapi.db.option("_netpack_beta", as_int=True)
            for version in self._versions:
                if version["draft"]:
                    continue

                if not allow_beta and version["prerelease"]:
                    continue

                yield version["tag_name"], version["assets"][0]["browser_download_url"]

        if args is not None and args["option"] != "_netpack_beta":
            return

        _netpack_version = UIField(
            "_netpack_version",
            "Firmware Version",
            desc="The netpack firmware version to install",
            field_type=UIFieldType.SELECT,
            options=[
                UIFieldSelectOption(
                    value=url,
                    label=tag,
                )
                for tag, url in generate_options()
            ],
        )
        self._rhapi.fields.register_option(_netpack_version, "netpack_panel")
        self._rhapi.ui.broadcast_ui("settings")

    def reset_dowload_status(self, args=None):
        if args is None or args["option"] != "_netpack_version":
            return

        self._downloaded = False


def initialize(rhapi):

    rhapi.ui.register_panel(
        "netpack_panel", "ELRS Netpack Firmware", "settings", order=0
    )

    _netpack_beta = UIField(
        "_netpack_beta",
        "Enable Beta",
        desc="Enables the installation of beta firmware",
        field_type=UIFieldType.CHECKBOX,
    )
    rhapi.fields.register_option(_netpack_beta, "netpack_panel")

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

    rhapi.events.on(
        Evt.OPTION_SET, installer.update_version_list, name="version_change"
    )

    rhapi.events.on(
        Evt.OPTION_SET, installer.reset_dowload_status, name="version_select_change"
    )
