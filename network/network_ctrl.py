import os
import paramiko
from log.logger import Logger
from network.webserver import WebServer
from network.remote_system import RemoteSystem
from typing import List


class NetworkCtrl:
    """
    The NetworkCtrl manages:
        1. Creates a Vlan and a Namespace
        2. Encapsulates the Vlan inside the Namespace
        3. Provides a SSH-Connection via paramiko
        4. Provides a WebServer
    """

    def __init__(self, remote_system: RemoteSystem):
        """
        Creats a VLAN and a Namespace for the specific RemoteSystem(Router,PowerStrip) and 'eth0' as the link-interface.
        The VLAN will be encapsulate in the Namespace.
        Also the a SSHClient will be created.

        :param remote_system: Could e a Router or a powerstrip object
        """
        self.remote_system = remote_system
        self.ssh = paramiko.SSHClient()

    def connect_with_remote_system(self):
        """
        Connects to the remote_system via SSH(Paramiko).
        Ignores a missing signatur.
        """
        Logger().info("Connect with RemoteSystem ...", 1)
        try:
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.ssh.connect(str(self.remote_system.ip), port=22,
                             username=str(self.remote_system.usr_name),
                             password=str(self.remote_system.usr_password))
            Logger().debug("[+] Successfully connected", 2)
        except Exception as e:
            Logger().error("[-] Couldn't connect", 2)
            raise e

    def send_command(self, command) -> List:
        """
        Sends the given command via SSH to the RemoteSystem.

        :param command: like "ping 8.8.8.8"
        :return: The output of the command given by the RemoteSystem
        """
        try:
            stdin, stdout, stderr = self.ssh.exec_command(command)
            output = stdout.readlines()
            Logger().debug("[+] Sent the command (" + command + ") to the RemoteSystem", 2)
            return output
        except Exception as e:
            Logger().error("[-] Couldn't send the command (" + command + ")", 2)
            raise e

    def send_data(self, local_file: str, remote_file: str):
        """
        Sends Data via sftp to the RemoteSystem

        :param local_file: Path to the local file
        :param remote_file: Path on the Router, where the file should be saved
        """
        try:
            # TODO: If sftp is installed on the Router
            '''
            sftp = self.ssh.open_sftp()
            sftp.put(local_file, remote_file)
            sftp.close()
            '''
            command = 'sshpass  -p' + str(self.remote_system.usr_password) + ' scp ' + local_file + ' ' + \
                      str(self.remote_system.usr_name) + '@' + str(self.remote_system.ip) + ':' + remote_file
            os.system(command)

            # TODO: Paramiko_scp have to installed
            '''
            scp = SCPClient(self.ssh.get_transport())
            scp.put(local_file, remote_file)
            '''
            Logger().debug("[+] Sent data '" + local_file + "' to RemoteSystem '" +
                           str(self.remote_system.usr_name) + "@" + str(self.remote_system.ip) +
                           ":" + remote_file + "'", 2)
        except Exception as e:
            Logger().error("[-] Couldn't send '" + local_file + "' to RemoteSystem '" +
                           str(self.remote_system.usr_name) + "@" + str(self.remote_system.ip) +
                           ":" + remote_file + "'", 2)
            Logger().error(str(e), 2)

    def remote_system_wget(self, file: str, remote_path: str, web_server_ip: str):
        """
        The RemoteSystem downloads the file from the PI and stores it at remote_file
        :param file: like /root/TestFramework/firmware/.../<firmware>.bin
        :param remote_path: like /tmp/
        :param web_server_ip: IP-address of the raspberryPI
        """
        webserver = WebServer()
        try:
            webserver.start()
            # Proves first if file already exists
            stout = self.send_command('test -f /' + remote_path + '/' + file.split('/')[-1] +
                                      ' || wget http://' + web_server_ip + ':' + str(WebServer.PORT_WEBSERVER) +
                                      file.replace(WebServer.BASE_DIR, '') + ' -P ' + remote_path)
        except Exception as e:
            Logger().error(str(e), 2)
        finally:
            webserver.join()

    def test_connection(self) -> bool:
        """
        Sends a 'Ping' to the RemoteSystem
        :return:
        """
        output = os.system("ping -c 1 " + str(self.remote_system.ip))
        if not output:
            return True
        else:
            return False
