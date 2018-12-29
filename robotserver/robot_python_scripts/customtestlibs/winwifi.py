import io
import os
import subprocess
import tempfile
import time
from typing import Callable, List, Optional
import wmi
import pythoncom


class WinWiFi:
    @classmethod
    def get_profile_template(cls) -> str:
        with open('data/profile-template.xml') as f:
            return f.read()

    @classmethod
    def netsh(cls, args: List[str], timeout: int = 3, check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(['netsh'] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=timeout, check=check, encoding='utf-8')
        except subprocess.CalledProcessError as e:
            raise RuntimeError('command {} return with error (code {}) :{}'.format(
                e.cmd, e.returncode, e.output))

    @classmethod
    def get_profiles(cls, interface: str, callback: Callable = lambda x: None) -> List[str]:
        profiles: List[str] = []

        raw_data: str = cls.netsh(
            ['wlan', 'show', 'profiles', 'interface={}'.format(interface)], check=False).stdout

        line: str
        for line in raw_data.splitlines():
            if ' : ' not in line:
                continue
            profiles.append(line.split(' : ', maxsplit=1)[1].strip())

        callback(raw_data)

        return profiles

    @classmethod
    def gen_profile(cls, ssid: str = '', auth: str = '', encrypt: str = '', passwd: str = '', remember: bool = True) \
            -> str:
        profile: str = cls.get_profile_template()

        profile = profile.replace('{ssid}', ssid)
        profile = profile.replace(
            '{connmode}', 'auto' if remember else 'manual')

        if auth == 'Open':
            profile = profile[:profile.index('<sharedKey>')] + \
                profile[profile.index('</sharedKey>')+len('</sharedKey>'):]
            profile = profile.replace('{auth}', 'open')
            profile = profile.replace('{encrypt}', 'none')
        elif passwd.strip():
            profile = profile.replace('{passwd}', passwd)
            profile = profile.replace('{auth}', auth)
            profile = profile.replace('{encrypt}', encrypt)
        else:
            raise AssertionError(
                "It should input password with security network!!")
        return profile

    @classmethod
    def add_profile(cls, profile: str, interface: str):
        fd: io.RawIOBase
        path: str
        fd, path = tempfile.mkstemp()

        os.write(fd, profile.encode())
        cls.netsh(['wlan', 'add', 'profile', 'filename={}'.format(
            path), 'interface={}'.format(interface)])

        os.close(fd)
        os.remove(path)

    @classmethod
    def delete_profile(cls, profile: str, interface: str):
        cls.netsh(['wlan', 'delete', 'profile', 'name={}'.format(
            profile), 'interface={}'.format(interface)])

    @classmethod
    def scan(cls, refresh: bool = False, interface: str = 'Wirless Network Connection', callback: Callable = lambda x: None) -> List['WiFiAp']:
        if not cls.is_interfaces_exist(interface):
            raise AssertionError(
                'The interface {} does not exist!'.format(interface))
        if refresh:
            cls.disable_interface(interface)
            cls.enable_interface(interface)
            time.sleep(5)
        cp: subprocess.CompletedProcess = cls.netsh(
            ['wlan', 'show', 'networks', 'mode=bssid', 'interface={}'.format(interface)])
        callback(cp.stdout)
        return list(map(WiFiAp.parse_netsh, [out for out in cp.stdout.split('\n\n') if out.startswith('SSID')]))

    @classmethod
    def get_interfaces(cls) -> List['WiFiInterface']:
        cp: subprocess.CompletedProcess = cls.netsh(
            ['wlan', 'show', 'interfaces'])
        return list(map(WiFiInterface.parse_netsh,
                        [out for out in cp.stdout.split('\n\n') if out.startswith('    Name')]))

    @classmethod
    def get_connected_interfaces(cls) -> List['WiFiInterface']:
        return list(filter(lambda i: i.state == WiFiConstant.STATE_CONNECTED, cls.get_interfaces()))

    @classmethod
    def is_interfaces_exist(cls, interface):
        return list(filter(lambda i: i.name == interface, cls.get_interfaces()))

    @classmethod
    def disable_interface(cls, interface: str):
        cls.netsh(['interface', 'set', 'interface', 'name={}'.format(
            interface), 'admin=disabled'], timeout=15)

    @classmethod
    def enable_interface(cls, interface: str):
        cls.netsh(['interface', 'set', 'interface', 'name={}'.format(
            interface), 'admin=enabled'], timeout=15)

    @classmethod
    def connect(cls, ssid: str, passwd: str = '', remember: bool = True, interface: str = 'Wirless Network Connection'):
        if not cls.is_interfaces_exist(interface):
            raise AssertionError(
                'the interface {} does not exist!'.format(interface))

        for _ in range(3):
            aps: List['WiFiAp'] = cls.scan(interface=interface)
            ap: 'WiFiAp'
            if ssid in [ap.ssid for ap in aps]:
                break
            time.sleep(5)
        else:
            raise RuntimeError('Cannot find Wi-Fi AP')

        # make sure the profile sync with AP
        if ssid in cls.get_profiles(interface):
            cls.delete_profile(ssid, interface)

        ap = [ap for ap in aps if ap.ssid == ssid][0]
        cls.add_profile(cls.gen_profile(
            ssid=ssid, auth=ap.auth, encrypt=ap.encrypt, passwd=passwd, remember=remember), interface)

        cls.netsh(['wlan', 'connect', 'name={}'.format(
            ssid), 'interface={}'.format(interface)])

        for _ in range(30):
            if list(filter(lambda it: it.ssid == ssid, WinWiFi.get_connected_interfaces())):
                break
            time.sleep(1)
        else:
            raise RuntimeError('Cannot connect to Wi-Fi AP')

    @classmethod
    def disconnect(cls):
        cls.netsh(['wlan', 'disconnect'])

    @classmethod
    def forget(cls, *ssids: str):
        for ssid in ssids:
            cls.netsh(['wlan', 'delete', 'profile', ssid])


class WiFiAp:
    @classmethod
    def parse_netsh(cls, raw_data: str) -> 'WiFiAp':
        ssid: str = ''
        auth: str = ''
        encrypt: str = ''
        bssid: str = ''
        strength: int = 0

        line: str
        for line in raw_data.splitlines():
            if ' : ' not in line:
                continue
            value: str = line.split(' : ', maxsplit=1)[1].strip()
            if line.startswith('SSID'):
                ssid = value
            elif line.startswith('    Authentication'):
                if '-Personal' in value:
                    value = value.replace('-Personal', 'PSK')
                auth = value
            elif line.startswith('    Encryption'):
                if value == 'CCMP':
                    value = 'AES'
                encrypt = value
            elif line.startswith('    BSSID'):
                bssid = value.lower()
            elif line.startswith('         Signal'):
                strength = int(value[:-1])
        return cls(ssid=ssid, auth=auth, encrypt=encrypt, bssid=bssid, strength=strength, raw_data=raw_data)

    def __init__(
            self,
            ssid: str = '',
            auth: str = '',
            encrypt: str = '',
            bssid: str = '',
            strength: int = 0,
            raw_data: str = '',
    ):
        self._ssid: str = ssid
        self._auth: str = auth
        self._encrypt: str = encrypt
        self._bssid: str = bssid
        self._strength: int = strength
        self._raw_data: str = raw_data

    @property
    def ssid(self) -> str:
        return self._ssid

    @property
    def auth(self) -> str:
        return self._auth

    @property
    def encrypt(self) -> str:
        return self._encrypt

    @property
    def bssid(self) -> str:
        return self._bssid

    @property
    def strength(self) -> int:
        return self._strength

    @property
    def raw_data(self) -> str:
        return self._raw_data


class WiFiConstant:
    STATE_CONNECTED = 'connected'
    STATE_DISCONNECTED = 'disconnected'


class WiFiInterface:
    @classmethod
    def parse_netsh(cls, raw_data: str) -> 'WiFiInterface':
        name: str = ''
        state: str = ''
        ssid: str = ''
        bssid: str = ''

        line: str
        for line in raw_data.splitlines():
            if ' : ' not in line:
                continue
            value: str = line.split(' : ', maxsplit=1)[1].strip()
            if line.startswith('    Name'):
                name = value
            elif line.startswith('    State'):
                state = value
            elif line.startswith('    SSID'):
                ssid = value
            elif line.startswith('    BSSID'):
                bssid = value

        c: 'WiFiInterface' = cls(name=name, state=state)
        if ssid:
            c.ssid = ssid
        if bssid:
            c.bssid = bssid
        return c

    def __init__(
            self,
            name: str = '',
            state: str = '',
            ssid: Optional[str] = None,
            bssid: Optional[str] = None,
    ):
        self._name: str = name
        self._state: str = state
        self._ssid: Optional[str] = ssid
        self._bssid: Optional[str] = bssid

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> str:
        return self._state

    @property
    def ssid(self) -> Optional[str]:
        return self._ssid

    @ssid.setter
    def ssid(self, value: str):
        self._ssid = value

    @property
    def bssid(self) -> Optional[str]:
        return self._bssid

    @bssid.setter
    def bssid(self, value: str):
        self._bssid = value


class WinIp:
    def __init__(self):
        pythoncom.CoInitialize()
        self.svc = wmi.WMI()

    def set_static_ip(self, interface, ipAddress, subnetMask):
        #svc = wmi.WMI()
        interfaceIndex = self.get_interface_index(interface)
        interfaces = self.svc.Win32_NetworkAdapterConfiguration(IPEnabled=True)
        for intf in interfaces:
            if intf.InterfaceIndex == interfaceIndex:
                ret = intf.EnableStatic(
                    IPAddress=ipAddress, SubnetMask=subnetMask)
                if ret[0] != 0:
                    raise AssertionError(
                        'set static ip failed, return code {}'.format(ret[0]))
                return
        raise AssertionError(
                        'set static ip failed, not found interface {}'.format(interface))

    def get_interface_index(self, interface):
        adpts = self.svc.Win32_NetworkAdapter()
        for adpt in adpts:
            if adpt.NetConnectionID and (adpt.NetConnectionID == interface):
                return adpt.InterfaceIndex
        raise AssertionError(
            'Can not  find interface index for {}'.format(interface))

    def ping(self, ipAddress):
        #svc = wmi.WMI()
        wql = "SELECT StatusCode FROM Win32_PingStatus WHERE Address = '{}'".format(
            ipAddress)
        for _ in range(3):
            for i in self.svc.query(wql):
                if i.StatusCode == 0:
                    return
        raise AssertionError(
            'Can not ping ip address {}'.format(ipAddress))


if __name__ == "__main__":
    WinWiFi.connect(ssid='ASUS', passwd='12345678',
                    remember=True, interface='无线网络连接')
