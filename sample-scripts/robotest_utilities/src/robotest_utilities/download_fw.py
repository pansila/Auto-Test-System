import os, sys
import subprocess
from pathlib import Path

class download_interface():
    def download(self, deviceName, firmwareName=None, flashAddr=None):
        dut = self.configDut[deviceName]
        if 'download' not in dut:
            raise AssertionError('Download method is not configured for {}'.format(deviceName))

        for d in dut['download']:
            if len(d) <= 1:
                print('download tool {} is not supported yet'.format(d['tool'] if 'tool' in d else d))
                continue

            if d['tool'].upper() == 'MDK':
                if os.name != 'nt':
                    print('MDK is only supported on Windows')
                    continue
                cmd = [d['path'], '-f', str(Path(d['workdir']) / d['project']), '-t', d['target']]
                subprocess.run(cmd, check=True)
                break

            if d['tool'].upper() == 'JLINK':
                if not firmwareName:
                    firmwareName = d['datafile']
                if not flashAddr:
                    flashAddr = d['flash_addr']
                    if not isinstance(d['flash_addr'], str):
                        flashAddr = '{:x}'.format(d['flash_addr'])
                if flashAddr.startswith('0x'):
                    flashAddr = flashAddr[2:]

                firmwarePath = Path(self.config["resource_dir"]) / firmwareName
                script = Path(self.config["tmp_dir"]) / 'download_script.jlink'
                script_contents = ("r\n"
                                   "exec EnableEraseAllFlashBanks\n"
                                   "erase\n"
                                   "loadbin {} {} SWDSelect\n"
                                   "verifybin {} {}\n"
                                   "r\n"
                                   "g\n"
                                   "qc\n".format(firmwarePath, flashAddr, firmwarePath, flashAddr))
                with open(script, 'w') as f:
                    f.write(script_contents)
                cmd = [d['path'], '-device', d['device'], '-if', d['interface'], '-speed', str(d['speed']), '-autoconnect', '1', '-JTAGConf', '-1,-1', '-CommanderScript', str(script)]
                subprocess.run(cmd, check=True)
                break
            print('Firmware downloading failed by {}, try next tool...'.format(d['tool'].upper()))
        else:
            raise AssertionError('Downloading firmware for {} failed'.format(deviceName))
