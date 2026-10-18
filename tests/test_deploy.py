import copy
import json
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch
from looi_deploy import cli

class DeployTests(unittest.TestCase):
    def setUp(self):
        self.profile={'version':1,'board':'n16r8','pins':dict(cli.BOARDS['n16r8']['default_pins'])}
    def test_device_names(self):
        for name in ["小乐", "一二三四五六七八", "Looi 42"]:
            self.assertEqual(cli.validate_device_name(name), name)
        for name in ["", "   ", "一二三四五六七八九", "a\n", "a" * 25]:
            with self.assertRaises(cli.DeployError): cli.validate_device_name(name)

    def test_gpio_validation(self):
        self.assertEqual(cli.validate_profile(self.profile),self.profile)
        for pin in [True,'17',17.5,0,3,19,20,33,38,43,44,45,46,48,49,16]:
            p=copy.deepcopy(self.profile);p['pins']['ena']=pin
            with self.assertRaises(cli.DeployError):cli.validate_profile(p)
    def test_preserves_existing_wiring(self):
        from argparse import Namespace
        self.profile['pins']['ena']=4
        args=Namespace(profile=None,use_default_pins=False,board='n16r8')
        self.assertEqual(cli.profile_from_args(args,{'hardware_configured':True,'hardware_profile':self.profile}),self.profile)
        with self.assertRaises(cli.DeployError):cli.profile_from_args(args,None)
    def test_first_install_needs_no_credential_input_for_either_board(self):
        for board in ('n16r8', 'n8r8'):
            with self.subTest(board=board):
                profile={'version':1,'board':board,'pins':dict(cli.BOARDS[board]['default_pins'])}
                ready={'device_id':'looi-112233445566','firmware_version':'9.4.2','hardware_profile':profile,
                       'flash_mb':cli.BOARDS[board]['flash_mb'],'physical_flash_bytes':cli.BOARDS[board]['flash_mb']*1024*1024,
                       'psram_bytes':8388608,'hardware_ready':True}
                named={**ready,'name':'LOOI-小乐','ap_ssid':'LOOI-小乐','device_name_custom':True}
                args=Namespace(command='install',port='fake',board=board,profile=None,use_default_pins=True,
                               assets=None,release='latest',password_stdin=False,name='小乐')
                with patch.object(cli,'load_release',return_value=({'version':'9.4.2'},[(0x8000,b'expected')])), \
                     patch.object(cli,'serial_request',side_effect=[cli.DeployError('blank board',4),{},{}]) as serial, \
                     patch.object(cli,'inspect_rom',return_value=(cli.BOARDS[board]['flash_mb'],b'expected')), \
                     patch.object(cli,'esptool'),patch.object(cli,'wait_for_device',side_effect=[ready,ready,named]), \
                     patch.object(cli,'record',return_value='local-record'),patch.object(cli.time,'sleep'), \
                     patch.object(cli.sys,'stdin') as stdin:
                    self.assertTrue(cli.run(args)['verified'])
                    stdin.readline.assert_not_called()
                    writes=[call.args[1] for call in serial.call_args_list if call.args[1]['type']!='hardware_get']
                    self.assertEqual([w['type'] for w in writes],['hardware_set','device_name_set'])
                    self.assertTrue(all(w['admin_password']==cli.INITIAL_ADMIN_PASSWORD for w in writes))
    def test_existing_device_credentials_can_be_supplied_explicitly(self):
        args=Namespace(port='fake',password_stdin=True)
        with patch.object(cli,'serial_request',return_value={'accepted':True}) as serial:
            cli.admin_request(args,{'type':'hardware_set','hardware_profile':self.profile},'owner-secret')
            self.assertEqual(serial.call_args.args[1]['admin_password'],'owner-secret')
    def test_existing_device_rejection_does_not_prompt_reset_or_retry(self):
        args=Namespace(port='fake',password_stdin=False)
        with patch.object(cli,'serial_request',side_effect=cli.DeployError('Device administrator password required',5)) as serial:
            with self.assertRaisesRegex(cli.DeployError,'--password-stdin'):
                cli.admin_request(args,{'type':'hardware_set','hardware_profile':self.profile},cli.INITIAL_ADMIN_PASSWORD)
            self.assertEqual(serial.call_count,1)
    def test_first_configuration_uses_initial_credential_and_keeps_existing_pins(self):
        self.profile['pins']['ena']=4
        ready={'device_id':'looi-112233445566','hardware_configured':True,'hardware_profile':self.profile,
               'flash_mb':16,'physical_flash_bytes':16777216,'psram_bytes':8388608,'hardware_ready':True}
        args=Namespace(command='configure',port='fake',board='n16r8',profile=None,use_default_pins=False,password_stdin=False,name=None)
        with patch.object(cli,'serial_request',side_effect=[ready,{}]) as serial, \
             patch.object(cli,'wait_for_device',return_value=ready),patch.object(cli,'record',return_value='local-record'), \
             patch.object(cli.time,'sleep'),patch.object(cli.sys,'stdin') as stdin:
            self.assertTrue(cli.run(args)['verified'])
            stdin.readline.assert_not_called()
            self.assertEqual(serial.call_args.args[1]['hardware_profile'],self.profile)
    def test_existing_device_stdin_is_read_without_replacing_its_credential(self):
        ready={'device_id':'looi-112233445566','hardware_configured':True,'hardware_profile':self.profile,
               'flash_mb':16,'physical_flash_bytes':16777216,'psram_bytes':8388608,'hardware_ready':True}
        args=Namespace(command='configure',port='fake',board='n16r8',profile=None,use_default_pins=False,password_stdin=True,name=None)
        with patch.object(cli,'serial_request',side_effect=[ready,{}]) as serial, \
             patch.object(cli,'wait_for_device',return_value=ready),patch.object(cli,'record',return_value='local-record'), \
             patch.object(cli.time,'sleep'),patch.object(cli.sys,'stdin',StringIO('owner-secret\n')):
            self.assertTrue(cli.run(args)['verified'])
            self.assertEqual(serial.call_args.args[1]['admin_password'],'owner-secret')
    def test_success_requires_full_readback(self):
        state={'hardware_profile':self.profile,'flash_mb':16,'physical_flash_bytes':16777216,'psram_bytes':8388608,'hardware_ready':True,'firmware_version':'2.1.0'}
        cli.verify_state(state,'n16r8',self.profile,'2.1.0')
        for override in [{'hardware_ready':False},{'physical_flash_bytes':8388608},{'psram_bytes':0},{'firmware_version':'2.0.2'}]:
            with self.assertRaises(cli.DeployError):cli.verify_state({**state,**override},'n16r8',self.profile,'2.1.0')
    def test_verify_does_not_require_a_fixed_version(self):
        state={'hardware_profile':self.profile,'flash_mb':16,'physical_flash_bytes':16777216,'psram_bytes':8388608,'hardware_ready':True,'firmware_version':'9.4.2'}
        self.assertEqual(cli.verify_state(state,'n16r8',self.profile),state)
        cli.verify_state(state,'n16r8',self.profile,'9.4.2')
        with self.assertRaises(cli.DeployError):
            cli.verify_state(state,'n16r8',self.profile,'9.4.1')
    def test_latest_uses_downloaded_version(self):
        data=f"LOOI_HW_V1|n16r8|1|{cli.BOARDS['n16r8']['partition']}|END".encode()
        parts=[{'offset':0x10000,'url':cli.RELEASE+'download/v9.4.2/app.bin','size':len(data),'sha256':cli.sha256(data)}]
        with patch.object(cli,'download',side_effect=[b'{"version":"9.4.2"}',data]) as fetch,patch.object(cli,'check_manifest',return_value=parts):
            manifest,images=cli.load_release('n16r8')
            self.assertEqual(manifest['version'],'9.4.2')
            self.assertEqual(images,[(0x10000,data)])
            self.assertEqual(fetch.call_args_list[0].args[0],cli.RELEASE+'latest/download/looi-s3-usb.json')
    def test_no_credentials_in_record(self):
        state={'device_id':'looi-112233445566','firmware_version':'2.1.0','hardware_profile':self.profile,'hardware_ready':True,'password':'SECRET','admin_password':'SECRET','ssid':'PRIVATE'}
        with tempfile.TemporaryDirectory() as temp,patch('looi_deploy.cli.Path',side_effect=lambda p:Path(temp)/p):
            path=cli.record(state);data=Path(path).read_text();self.assertNotIn('SECRET',data);self.assertNotIn('PRIVATE',data)
    def test_rejects_untrusted_downloads(self):
        for url in ['http://github.com/xlle-er/LOOI-DF26-Firmware/releases/x','https://github.com/other/repo/releases/x','https://github.com.evil.example/x','https://user:pw@github.com/xlle-er/LOOI-DF26-Firmware/releases/x']:
            self.assertFalse(cli.trusted_url(url))
    def test_explicit_release_validation(self):
        with self.assertRaises(cli.DeployError):cli.load_release('n16r8',release='../evil')
        with patch.object(cli,'download',return_value=b'{"version":"2.0.2"}') as fetch:
            with self.assertRaisesRegex(cli.DeployError,'version differ'):cli.load_release('n16r8',release='v2.1.0')
            self.assertIn('/download/v2.1.0/looi-s3-usb.json',fetch.call_args.args[0])
    def test_local_release_checks_all_segments(self):
        source=Path(__file__).resolve().parents[2]/'LOOI-DF26-Firmware/dist'
        if not (source/'looi-s3-usb.json').exists():self.skipTest('No local release build')
        manifest,images=cli.load_release('n16r8',source)
        self.assertEqual(len(images),4);self.assertEqual(manifest['version'],json.loads((source/'looi-s3-usb.json').read_text())['version'])
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)
            for p in source.glob('looi-s3*'):
                if p.is_file(): (dest/p.name).write_bytes(p.read_bytes())
            app=dest/'looi-s3-LooiWifiOta.ino.bin';app.write_bytes(app.read_bytes()[:-1])
            with self.assertRaises(cli.DeployError):cli.load_release('n16r8',dest)
    def test_install_unknown_partition_never_writes(self):
        from argparse import Namespace
        args=Namespace(command='install',port='fake',board='n16r8',profile=None,use_default_pins=True,assets=None)
        images=[(0x8000,b'expected')]
        with patch.object(cli,'load_release',return_value=({'version':'2.1.0'},images)),patch.object(cli,'serial_request',side_effect=cli.DeployError('old firmware',4)),patch.object(cli,'inspect_rom',return_value=(16,b'unknown')),patch.object(cli,'esptool') as esp:
            with self.assertRaises(cli.DeployError):cli.run(args)
            esp.assert_not_called()
    def test_flash_size_mismatch_never_writes(self):
        from argparse import Namespace
        args=Namespace(command='install',port='fake',board='n16r8',profile=None,use_default_pins=True,assets=None)
        with patch.object(cli,'load_release',return_value=({'version':'2.1.0'},[(0x8000,b'expected')])),patch.object(cli,'serial_request',side_effect=cli.DeployError('old firmware',4)),patch.object(cli,'inspect_rom',return_value=(8,b'expected')),patch.object(cli,'esptool') as esp:
            with self.assertRaises(cli.DeployError):cli.run(args)
            esp.assert_not_called()
if __name__=='__main__':unittest.main()
