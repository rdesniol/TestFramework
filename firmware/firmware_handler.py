from firmware.firmware import Firmware
from log.loggersetup import LoggerSetup
import urllib.request
import re
import os
import errno
import logging

# This is your Project Root
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
# Join the path to the webserver files with firmwares
FIRMWARE_PATH = os.path.join(BASE_DIR, 'firmware/firmwares')


class FirmwareHandler:
    """
    The FirmwareHandler manages:
        1. The import of existing Firmwares stored in 'TestFramework/firmware/firmwares'
        2. The correct download of the Manifest for a given release_model(stable, beta, experimental)
        3. The correct download of a single or all Firmwares for a given release_model(stable, beta, experimental)
        4. Creates the Firmware-Objects and lists them
    """""

    # There would also be 'factory'
    UPDATE_TYPE = "sysupgrade"

    def __init__(self, url: str):
        """
        :param url: URL of the server where the firmware-image can be downloaded.
        """
        self.firmwares = []
        self.url = url

    def get_firmware(self, router_model: str, release_model: str, download_all: bool) -> Firmware:
        """
        Returns the correct Firmware of a Router_Model and in the specific Release_Model.

        :param router_model: Like 'TP-LINK TL-WR841N/ND v9'
        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :param download_all: If all Firmwares in the Manifest should be downloaded
        :return: Firmware-Obj
        """
        self.import_firmwares(release_model)

        if download_all:
            self.firmwares = self.download_all_firmwares(release_model)
        else:
            firmware = self.get_stored_firmware(router_model)
            if firmware is not None:
                return firmware
            firmware = self.download_firmware(router_model, release_model)
            if firmware is not None:
                self.firmwares.append(firmware)
        return self.get_stored_firmware(router_model)

    def get_stored_firmware(self, router_model: str) -> Firmware:
        """
        Returns the matching Firmware, if stored in the list 'self.firmwares'.

        :param router_model: Like 'TP-LINK TL-WR841N/ND v9'
        :return: Firmware-Obj
        """
        router_model_name, router_model_version = self._parse_router_model(router_model)
        parsed_router_model = router_model_name + "-" + router_model_version
        for firmware in self.firmwares:
            if parsed_router_model in firmware.name:
                logging.info("%s[+] The Firmware is up to date", LoggerSetup.get_log_deep(2))
                return firmware
        logging.info("%s[-] Couldn't found a matching Firmware to Router(" + router_model + ")",
                     LoggerSetup.get_log_deep(2))
        return None

    def _verified_download(self, firmware: Firmware, hash_firmware: str, max_attempts: int) -> bool:
        """
        Downloads the given Firmware and checks if the download was correct and if the hash is matching.

        :param firmware: Firmware-Obj
        :param hash_firmware: Expected hash
        :param max_attempts: Maximal number of attempts to download a Firmware
        :return: 'True' if the Firmware could be downloaded and the hash is correct
        """
        valid_download = False
        count = 0
        while (not valid_download) & (count < max_attempts):
            valid_download = self._download_file(firmware.url, firmware.file, firmware.release_model)
            if valid_download:
                valid_download = firmware.check_hash(hash_firmware)
            count += 1
        if count >= max_attempts:
            logging.warning("%s[-] The Firmware(" + firmware.name + ") couldn't be downloaded",
                            LoggerSetup.get_log_deep(3))
            return False
        else:
            logging.info("%s[+] The Firmware(" + firmware.name + ") was successfully downloaded",
                         LoggerSetup.get_log_deep(3))
            return True

    def download_firmware(self, router_model: str, release_model: str, max_attemps: int=3) -> Firmware:
        """
        Downloads only one Firmware which matches a Firmware in the Manifest.

        :param router_model: Like 'TP-LINK TL-WR841N/ND v9'
        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :param max_attemps: Maximal number of attempts to download a Firmware
        :return: Firmware-Obj
        """
        logging.info("%sDownload single Firmware ...", LoggerSetup.get_log_deep(2))
        firmwares, hashs = self._get_all_firmwares(release_model)
        router_model_name, router_model_version = self._parse_router_model(router_model)
        parsed_router_model = router_model_name + "-" + router_model_version
        for i, firmware in enumerate(firmwares):
            if parsed_router_model in firmware.name:
                self._verified_download(firmware, hashs[i], max_attemps)
                return firmware
        return None

    def download_all_firmwares(self, release_model: str, max_attemps: int=3):
        """
        Downloads all Firmwares which are found in the Manifest and proves the hash.
        If a download more than 3 times fails, the file will not be downloaded.

        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :param max_attemps: Maximal number of attempts to download a Firmware
        :return: A List of all Firmware-Obj
        """
        logging.info("%sDownload all Firmwares ...", LoggerSetup.get_log_deep(2))
        firmwares, hashs = self._get_all_firmwares(release_model)
        num_firmwares = len(firmwares)
        for i, firmware in enumerate(firmwares):
            valid_download = self._verified_download(firmware, hashs[i], max_attemps)
            if not valid_download:
                del(firmwares[i])
                del(hashs[i])
        logging.info("%s" + str(len(firmwares)) + "/" + str(num_firmwares) + " Firmwares downloaded",
                     LoggerSetup.get_log_deep(3))
        return firmwares

    def _get_all_firmwares(self, release_model: str):
        """
        Creats a list of Firmwares and a list of related hashs.
        All Firmwares are given from the Manifest which is downloaded first.

        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :return: Tuple of a list of Firmware-Obj and a list of hashs
        """
        firmwares = []
        hashs = []
        non_parsed_firmwares = self._read_firmwares_from_manifest(release_model)
        for firmware in non_parsed_firmwares:
            if firmware.find("---\n") != -1:  # skip the end of the file
                continue
            firmware_name = "gluon" + firmware.split("gluon")[1].split("-sysupgrade")[0] + "-" + \
                            FirmwareHandler.UPDATE_TYPE + "." + firmware.split(".")[-1].replace("\n", "")
            hash_firmware = firmware.split(' ')[4]
            freifunk_verein = firmware_name.split('-')[1]
            firmware_version = firmware_name.split('-')[2]
            file = (FIRMWARE_PATH + '/' + release_model + '/' + FirmwareHandler.UPDATE_TYPE + '/' +
                    firmware_name)
            url = self.url + '/' + release_model + '/' + FirmwareHandler.UPDATE_TYPE + '/' + firmware_name
            firmwares.append(Firmware(firmware_name, firmware_version, freifunk_verein, release_model, file, url))
            hashs.append(hash_firmware)
        return [firmwares, hashs]

    def _read_firmwares_from_manifest(self, release_model: str) -> str:
        """
        Creates a list of non pared Firmware_names from the Manifest.

        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :return: List of Firmwares written like in the Manifest
        """
        logging.debug("%sCreate a list of firmwares from the manifest ...", LoggerSetup.get_log_deep(3))
        file = self._download_manifest(release_model)
        firmwares = []
        with open(file, 'r') as f:
            for i, line in enumerate(f):
                if i >= 4:
                    firmware = "[" + str(i - 4) + "]  " + line
                    firmwares.append(firmware)
            firmwares = firmwares[:-3]
            f.close()
        return firmwares

    def firmware_available_in_manifest(self, release_model: str, firmware_name: str) -> bool:
        """
        Checks if the given Firmware is written inside the Manifest.

        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :param firmware_name: Including: router_model_name, router_model_version, firmware_version, freifunk_verein
        :return: 'True' if the Firmware_name was found in the Manifest
        """
        file = (FIRMWARE_PATH + '/' + release_model + '/' + FirmwareHandler.UPDATE_TYPE + '/' +
                release_model + '.manifest')
        with open(file, 'r') as f:
            for line in f:
                if firmware_name in line:
                    return True
        return False

    def _download_file(self, url: str, file: str, release_model: str) -> bool:
        """
        Downloads the Firmware from the URL and saves it into the given file.

        :param url: URL of the server where the firmware-image can be downloaded
        :param file: The path/file where the Firmware should be stored on the device
        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :return: 'True' if the Firmware was successfully downloaded
        """
        logging.debug("%sDownload " + url + " ...", LoggerSetup.get_log_deep(3))
        self._create_path(FIRMWARE_PATH + '/' + release_model + '/' + FirmwareHandler.UPDATE_TYPE)
        try:
            # Download the file from `url` and save it locally under `file_name`:
            urllib.request.urlretrieve(url, file)
            return True
        except Exception as e:
            logging.debug("%s[-] Failed download", LoggerSetup.get_log_deep(3))
            logging.error("%s" + str(e), LoggerSetup.get_log_deep(3))
            return False

    def _download_manifest(self, release_model: str, max_count: int=3) -> str:
        """
        Downloads the manifest and saves it.Builds from the URL a path.

        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        :return: The path/file where the Firmware should be stored on the device
        """
        url = (self.url + '/' + release_model + '/' + FirmwareHandler.UPDATE_TYPE + '/' +
               release_model + '.manifest')
        file = (FIRMWARE_PATH + '/' + release_model + '/' + FirmwareHandler.UPDATE_TYPE + '/' +
                release_model + '.manifest')
        valid_download = False
        count = 0
        while (not valid_download) & (count < max_count):
            valid_download = self._download_file(url, file, release_model)
            count += 1
        if count >= max_count:
            logging.debug("%s[-] Couldn't download manifest", LoggerSetup.get_log_deep(3))
            return ""
        else:
            logging.debug("%s[+] Successfully downloaded manifest", LoggerSetup.get_log_deep(3))
            return file

    def _parse_router_model(self, router_model: str):
        """
        Transform a str like "TP-LINK TL-WR841N/ND v9" into "tp-link-tl-wr841n-nd-v9".

        :param router_model:  Like 'TP-LINK TL-WR841N/ND v9'
        :return: Router_model_name and Router_model_version
        """
        logging.debug("%sParse RouterModel ...", LoggerSetup.get_log_deep(3))
        tmp = router_model.split(' v')
        router_model_name = tmp[0]
        router_model_version = 'v' + tmp[1]
        router_model_name = router_model_name.lower()
        # replace all symbols with a minus
        router_model_name = re.sub(r'(?:[^\w])', '-', router_model_name)
        logging.debug("%s'" + router_model + "' into '" + router_model_name + " " + router_model_version + "'",
                      LoggerSetup.get_log_deep(3))
        return [router_model_name, router_model_version]

    def _create_path(self, path: str):
        """
        Creates directories if necessary.

        :param path: Path where the firmware-image should be stored on the device
        """
        try:
            logging.debug("%sCreate path " + path + " ...", LoggerSetup.get_log_deep(4))
            os.makedirs(path)
            logging.debug("%s[+] Path successfully created", LoggerSetup.get_log_deep(5))
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise e
            logging.debug("%s[+] Path allready exists", LoggerSetup.get_log_deep(5))

    def import_firmwares(self, release_model: str):
        """
        Imports the stored Firmwares, so the Firmware_Handler can use them.

        :param release_model: Can be set to: 'stable', 'beta' or 'experimental'. Used in the url
        """
        path = FIRMWARE_PATH + '/' + release_model + '/' + self.UPDATE_TYPE + '/'
        logging.debug("%sImport Firmwares from '" + path + "'", LoggerSetup.get_log_deep(2))
        count = 0

        try:
            files = os.listdir(path)
        except Exception:
            logging.warning("%s[!] No Firmwares available for import at path '" + path + "'",
                            LoggerSetup.get_log_deep(3))
            return

        for firmware_name in files:
            try:
                freifunk_verein = firmware_name.split('-')[1]
                firmware_version = firmware_name.split('-')[2]
                file = path + firmware_name
                url = self.url + '/' + release_model + '/' + self.UPDATE_TYPE + '/' + firmware_name
                self.firmwares.append(Firmware(firmware_name, firmware_version, freifunk_verein,
                                               release_model, file, url))
                count += 1
            except Exception:
                logging.warning("%s[-] Couldn't import " + firmware_name, LoggerSetup.get_log_deep(3))
                continue
        logging.debug("%s[+] " + str(count) + " Firmwares imported", LoggerSetup.get_log_deep(3))
