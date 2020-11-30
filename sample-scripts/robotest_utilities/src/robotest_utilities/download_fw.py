import asyncio
import os, sys
import subprocess
import tempfile
from pathlib import Path

class download_fw_intf():
    async def dut_download(self, deviceName, firmwareName=None, flashAddr=None):
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
                p = await asyncio.create_subprocess_exec(cmd[0], *(cmd[1:]), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await p.communicate()
                if p.returncode:
                    print(f'MDK programmer return code: {p.returncode}')
                    print('stdout: ' + stdout.decode())
                    print('stderr: ' + stderr.decode())
                    continue
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

                firmwarePath = Path("resources") / 'test_data' / firmwareName
                if not firmwarePath.exists():
                    raise AssertionError(f'Firmware {firmwarePath} not found')
                with tempfile.TemporaryDirectory() as tempDir:
                    script = Path(tempDir) / 'download_script.jlink'
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
                    p = await asyncio.create_subprocess_exec(cmd[0], *(cmd[1:]), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    stdout, stderr = await p.communicate()
                    if p.returncode:
                        print(f'JLINK programmer return code: {p.returncode}')
                        print('stdout: ' + stdout.decode())
                        print('stderr: ' + stderr.decode())
                        continue
                break
            if d['tool'].upper() == 'DAPLINK':
                if not firmwareName:
                    firmwareName = d['datafile']
                if not os.path.isabs(firmwareName):
                    firmwarePath = Path("resources") / 'test_data' / firmwareName
                cmd = ['pyocd.exe', 'flash', str(firmwarePath), '--probe', '0', '--target', d['target']]
                p = await asyncio.create_subprocess_exec(cmd[0], *(cmd[1:]), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await p.communicate()
                if p.returncode:
                    print(f'DAPLINK programmer return code: {p.returncode}')
                    print('stdout: ' + stdout.decode())
                    print('stderr: ' + stderr.decode())
                    continue
                break
            print('Firmware downloading failed by {}, try next tool...'.format(d['tool'].upper()))
        else:
            raise AssertionError('Failed to download the firmware for {}'.format(deviceName))
