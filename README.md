# ELRS Netpack Installer

A small RotorHazard plugin to assist with installing
the [ELRS Netpack](https://github.com/i-am-grub/elrs-netpack) 
firmware.


## Flashing ELRS Netpack

1. Download the [netpack-installer](https://github.com/i-am-grub/netpack-installer) plugin from the community plugins
list.

> [!NOTE]
> It may take awhile for the plugin install to finish due to installing the esptool python package

2. Connect the required ESP32 devkit to your timer over USB
3. In the `ELRS Netpack Firmware` panel (found on the `Settings` page), select the firmware version to install
4. Select the serial port of the connected device
5. Press the `Flash Netpack Firmware` button and wait for the flashing process to finish
6. If flashing was successful, disconnect the USB connection and use as desired