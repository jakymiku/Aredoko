"""Packaged activation guards and real owned-backend cleanup, generated inputs only."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import packaged_frontend as native
import package_release as packer
import test_release_staging as staging
import test_release_lifecycle as lifecycle


def make_msix(path, *, payload=None, identity='', extra=None):
    manifest = f'''<Package xmlns="{native.NS['m']}"><Identity Name="{native.PACKAGE_NAME}"
        Publisher="{native.PACKAGE_PUBLISHER}" ProcessorArchitecture="x64" Version="1.0.0.0" {identity}/>
        <Dependencies/><Applications><Application Id="App" Executable="Aredoko.WinUI.exe"
        EntryPoint="Windows.FullTrustApplication"/></Applications></Package>'''
    with zipfile.ZipFile(path, 'x') as output:
        output.writestr('AppxManifest.xml', manifest)
        for name in native.PAYLOAD:
            output.writestr(name, payload[name] if payload else ('fixture:' + name).encode())
        if extra:
            for name, data in extra.items():
                info = zipfile.ZipInfo('placeholder');info.filename = name
                output.writestr(info, data)


class ActivationPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aredoko-activation-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.msix = self.base / 'generated frontend.msix'

    def test_inspection_is_bounded_read_only_and_does_not_extract(self):
        make_msix(self.msix)
        before = self.msix.read_bytes(), self.msix.stat().st_mtime_ns
        expected = native.inspect_msix(self.msix)
        self.assertEqual(expected['name'], native.PACKAGE_NAME)
        self.assertEqual(len(expected['entries']), 6)
        self.assertEqual(before, (self.msix.read_bytes(), self.msix.stat().st_mtime_ns))
        self.assertEqual(list(self.base.iterdir()), [self.msix])

    def test_unsafe_archive_names_and_case_duplicates_rejected(self):
        for index, name in enumerate(('../outside', 'bad\\file', 'NUL.txt', 'AREdoko.WinUI.exe')):
            path = self.base / f'{index}.msix'
            make_msix(path, extra={name: b'bad'})
            with self.subTest(name=name), self.assertRaises(ValueError):native.inspect_msix(path)

    def test_wrong_identity_or_dependency_rejected(self):
        make_msix(self.msix)
        with zipfile.ZipFile(self.msix) as original:
            contents = {entry.filename: original.read(entry) for entry in original.infolist()}
        xml = contents['AppxManifest.xml']
        for index, modified in enumerate((xml.replace(b'x64', b'arm64'),
                xml.replace(b'AppPublisher', b'OtherPublisher'),
                xml.replace(b'<Dependencies/>', b'<Dependencies><PackageDependency Name="runtime"/></Dependencies>'),
                xml.replace(b'Windows.FullTrustApplication', b'Other.EntryPoint'))):
            path = self.base / f'wrong{index}.msix'
            with zipfile.ZipFile(path, 'x') as out:
                for name, data in contents.items():out.writestr(name, modified if name == 'AppxManifest.xml' else data)
            with self.subTest(index=index), self.assertRaises(ValueError):native.inspect_msix(path)

    def registration(self):
        family = native.PACKAGE_NAME + '_abcdefghijkl1'
        return {'Name': native.PACKAGE_NAME, 'Publisher': native.PACKAGE_PUBLISHER, 'Version': '1.0.0.0',
                'Architecture': 'X64', 'IsDevelopmentMode': False, 'PackageFamilyName': family,
                'PackageFullName': native.PACKAGE_NAME + '_1.0.0.0_x64__abcdefghijkl1',
                'InstallLocation': str(self.base / 'installed')}

    def test_registration_must_be_exact_and_non_development(self):
        make_msix(self.msix)
        expected = native.inspect_msix(self.msix)
        value = self.registration()
        self.assertTrue(native.validate_registration(value, expected)['aumid'].endswith('!App'))
        for key, bad in (('Version', '2.0.0.0'), ('Publisher', 'CN=other'), ('Architecture', 'arm64'),
                         ('IsDevelopmentMode', True), ('IsDevelopmentMode', None), ('PackageFamilyName', 'another'),
                         ('PackageFullName', 'another'), ('InstallLocation', '../relative')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                native.validate_registration({**value, key: bad}, expected)

    def test_reused_process_wrong_image_or_package_never_grants_ownership(self):
        native.validate_process_identity(101, 100, 'frontend.exe', Path('frontend.exe'), 'package', 'package')
        for created, image, package in ((99, 'frontend.exe', 'package'),
                (101, 'another.exe', 'package'), (101, 'frontend.exe', 'another-package')):
            with self.subTest(created=created, image=image, package=package), self.assertRaisesRegex(RuntimeError, 'left untouched'):
                native.validate_process_identity(created, 100, image, Path('frontend.exe'), package, 'package')

    def install_fixture(self):
        make_msix(self.msix, extra={'resources.pri': b'resource fixture'})
        expected = native.inspect_msix(self.msix)
        directory = self.base / 'installed';directory.mkdir()
        with zipfile.ZipFile(self.msix) as package:
            for entry in expected['entries']:
                target = directory / entry['path'];target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(entry['path']))
        registration = native.validate_registration(self.registration(), expected)
        return expected, registration

    def test_every_installed_file_including_resources_is_verified(self):
        expected, registration = self.install_fixture()
        self.assertEqual(native.verify_installed(expected, registration).name, 'Aredoko.WinUI.exe')
        for entry in expected['entries']:
            path = registration['directory'] / entry['path']
            original = path.read_bytes()
            path.write_bytes(b'X' * len(original))
            with self.subTest(path=entry['path']), self.assertRaises(ValueError):native.verify_installed(expected, registration)
            path.write_bytes(original)

    def test_queued_package_change_is_rejected_before_activation(self):
        expected, registration = self.install_fixture()
        frontend = native.PackagedFrontend(expected, registration)
        (registration['directory'] / 'resources.pri').write_bytes(b'changed')
        with patch.object(native, 'activate_application') as activate, self.assertRaises(ValueError):
            frontend.start([], Mock())
        activate.assert_not_called()

    def test_old_stage_cannot_silently_launch_direct_executable(self):
        with patch.object(native, 'activate_application') as activate, self.assertRaisesRegex(ValueError, 'frontend-msix'):
            native.prepare_frontend(self.base, {})
        activate.assert_not_called()

    def test_start_uses_exact_aumid_argv_and_closes_owned_handle_on_log_failure(self):
        expected, registration = self.install_fixture()
        frontend = native.PackagedFrontend(expected, registration)
        args = ['--viewer-settings', str(self.base/'日本語 with spaces.json'), '--ui-theme', 'dark']
        log = Mock();log.write.side_effect = OSError('disk full')
        process = Mock()
        with patch.object(native, 'activate_application', return_value=42) as activate, patch.object(native, 'WindowsProcess', return_value=process) as owned:
            with self.assertRaises(OSError):frontend.start(args, log)
        activate.assert_called_once_with(registration['aumid'], args)
        self.assertEqual(owned.call_args.args[:3], (42, frontend.executable, registration['full_name']))
        process.terminate.assert_called_once();process.wait.assert_called_once();process.close.assert_called_once()


class PackagedStagingTests(unittest.TestCase):
    setUp = staging.ReleaseStagingTests.setUp
    def test_matching_msix_is_copied_and_bound_to_complete_release(self):
        path = self.base / 'frontend.msix';make_msix(path)
        result = packer.package(self.output, skip_build=True, frontend_msix=path)
        self.assertEqual(result['frontend_activation'], 'msix')
        self.assertEqual(path.read_bytes(), (self.output/native.PACKAGE_PATH).read_bytes())
        self.assertEqual(packer.compute_sha256(path), next(e['sha256'] for e in result['entries'] if e['path'] == native.PACKAGE_PATH))
        from release_runtime import verify_release
        verify_release(self.output)

    def test_msix_publish_payload_supplies_bin_without_rebuilding_or_using_stale_build(self):
        path = self.base / 'frontend.msix'
        payload = {name: ('published:' + name).encode() for name in native.PAYLOAD}
        make_msix(path, payload=payload)
        with patch.object(packer.subprocess, 'run') as build:
            packer.package(self.output, frontend_msix=path)
        build.assert_not_called()
        for name, value in payload.items():self.assertEqual((self.output/'bin'/name).read_bytes(), value)
        self.assertFalse((self.output/'bin/AppX').exists())


class ActivationLifecycleTests(unittest.TestCase):
    setUp = lifecycle.ReleaseLifecycleTests.setUp
    session = lifecycle.ReleaseLifecycleTests.session
    backend = lifecycle.ReleaseLifecycleTests.backend
    assert_released = lifecycle.ReleaseLifecycleTests.assert_released
    def test_native_factory_failure_cleans_real_backend(self):
        start = Mock(side_effect=OSError('activation refused'))
        with self.assertRaisesRegex(OSError, 'activation refused'):self.session(app_factory=start)
        start.assert_called_once();self.assert_released()

    def test_backend_crash_terminates_and_closes_only_owned_frontend(self):
        original = subprocess.Popen
        children = []
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        frontend = Mock(returncode=0)
        def start(args, log):
            children[0].kill()
            children[0].wait(timeout=5)
            return frontend
        frontend.poll.return_value = None
        with patch('launch_release.subprocess.Popen', side_effect=spawn), self.assertRaisesRegex(RuntimeError, 'stopped unexpectedly'):
            self.session(app_factory=start)
        frontend.terminate.assert_called_once();frontend.wait.assert_called_once();frontend.close.assert_called_once()
        self.assert_released()

    def test_native_adapter_exit_releases_handle_and_real_backend(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        self.session(app_factory=Mock(return_value=process))
        process.close.assert_called_once();process.terminate.assert_not_called()
        self.assert_released()

    def test_native_failure_closes_handle_and_real_backend(self):
        process = Mock(returncode=7)
        process.poll.return_value = 7
        with self.assertRaisesRegex(RuntimeError, 'exited with code'):self.session(app_factory=Mock(return_value=process))
        process.close.assert_called_once();self.assert_released()


@unittest.skipUnless(os.name == 'nt', 'Native Windows process and COM checks')
class WindowsActivationTests(unittest.TestCase):
    def test_com_unknown_identity_fails_without_launching_a_known_application(self):
        aumid = 'Aredoko.NeverInstalledTestIdentity_0000000000000!Missing'
        with self.assertRaises(OSError):native.activate_application(aumid, ['日本語 with spaces'])

    def test_unpackaged_real_process_is_never_adopted_or_terminated(self):
        process = subprocess.Popen([sys.executable, '-B', '-c', 'import time;time.sleep(20)'],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with self.assertRaisesRegex(RuntimeError, 'ownership was not proven'):
                native.WindowsProcess(process.pid, Path(sys.executable), 'not-a-package', 0)
            self.assertIsNone(process.poll())
        finally:
            process.terminate();process.wait(timeout=5)


if __name__ == '__main__':unittest.main()
