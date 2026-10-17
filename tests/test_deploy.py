import copy
import json
from pathlib import Path
import tempfile
import unittest
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
    def test_success_requires_full_readback(self):
        state={'hardware_profile':self.profile,'flash_mb':16,'physical_flash_bytes':16777216,'psram_bytes':8388608,'hardware_ready':True,'firmware_version':'2.1.0'}
        cli.verify_state(state,'n16r8',self.profile,'2.1.0')
        for override in [{'hardware_ready':False},{'physical_flash_bytes':8388608},{'psram_bytes':0},{'firmware_version':'2.0.2'}]:
            with self.assertRaises(cli.DeployError):cli.verify_state({**state,**override},'n16r8',self.profile,'2.1.0')
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
        self.assertEqual(len(images),4);self.assertEqual(manifest['version'],'2.1.0')
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
