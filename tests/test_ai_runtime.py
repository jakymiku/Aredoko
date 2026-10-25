"""Synthetic runtime inventories; never executes selected Python/torch/models."""
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
from ai_profiles import DEFAULT_PROFILE
from ai_runtime import FORMAT,MARKER,REQUIRED_MODULES,inspect_runtime,model_state,legacy_runtime_state
from ai_runtime_preferences import AIRuntimePreferences,read_preferences,runtime_python
from runtime_paths import worker_command,bind_runtime,runtime_verification_status,start_runtime_verification,verify_runtime_pack,_verified_packs,_pack_bindings,_verify_state
from prepare_ai_runtime_pack import prepare
from launch_release import validate_settings


def fixture(directory,*,source=False):
    directory.mkdir()
    names={'python.exe','pythonw.exe','LICENSE.txt','python311.dll','python311.zip','python311._pth',
           *(f'Lib/site-packages/{m}/__init__.py' for m in REQUIRED_MODULES),
           'Lib/site-packages/torch/version.py','Lib/site-packages/torch/lib/generated.dll'}
    for name in names:
        path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture '+name.encode())
    header=bytearray(512);header[:2]=b'MZ';struct.pack_into('<I',header,60,128)
    header[128:132]=b'PE\0\0';struct.pack_into('<H',header,132,0x8664)
    (directory/'python.exe').write_bytes(header)
    (directory/'DLLs').mkdir()
    (directory/'python311._pth').write_text('python311.zip\n.\nDLLs\nLib/site-packages\nimport site\n')
    (directory/'Lib/site-packages/torch/version.py').write_text("__version__='2.9.1+cpu'\ncuda=None\n")
    if not source:seal(directory)
    return directory


def seal(directory):
    names=sorted(p for p in directory.rglob('*') if p.is_file() and p.name!=MARKER)
    entries=[{'path':p.relative_to(directory).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in names]
    value={'format':FORMAT,'abi':{'python':'3.11','architecture':'x64','engine':'pytorch','compute':'cpu',
        'torch':'2.9.1+cpu','cuda':None,'modules':list(REQUIRED_MODULES)},'entries':entries,
        'files_count':len(entries),'total_bytes':sum(e['bytes'] for e in entries)}
    (directory/MARKER).write_text(json.dumps(value),encoding='utf-8')
    return value


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='aredoko-ai-pack-');self.addCleanup(temp.cleanup)
        self.base=Path(temp.name);self.pack=fixture(self.base/'pack')
        _verified_packs.clear();_pack_bindings.clear();_verify_state.clear()

    def change(self,operation):
        path=self.pack/MARKER;value=json.loads(path.read_text());operation(value);path.write_text(json.dumps(value))

    def test_full_inventory_is_checked_without_execution(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No code execution')):
            info=inspect_runtime(self.pack,verify=True)
        self.assertEqual(info['verification'],'full');self.assertEqual(info['abi']['compute'],'cpu')
        self.assertFalse(info['driver_tested']);self.assertFalse(info['model_loaded'])

    def test_core_hash_and_x64_header_are_required(self):
        exe=self.pack/'python.exe';exe.write_bytes(b'not executable')
        with self.assertRaisesRegex(ValueError,'x64'):inspect_runtime(self.pack)

    def test_wrong_abi_and_duplicate_or_unsafe_paths_are_rejected(self):
        original=(self.pack/MARKER).read_bytes()
        operations=[lambda v:v['abi'].update(architecture='arm64'),
                    lambda v:v['abi'].update(compute='cuda',cuda=None),
                    lambda v:v['entries'][0].update(path='../outside'),
                    lambda v:v['entries'].append(v['entries'][0].copy())]
        for operation in operations:
            (self.pack/MARKER).write_bytes(original);self.change(operation)
            with self.subTest(operation=operation),self.assertRaises(ValueError):inspect_runtime(self.pack)

    def test_same_size_bulk_corruption_and_unknown_file_fail_full(self):
        bulk=self.pack/'Lib/site-packages/torch/lib/generated.dll';before=bulk.read_bytes()
        bulk.write_bytes(b'x'*len(before))
        self.assertEqual(inspect_runtime(self.pack)['verification'],'core_only')
        with self.assertRaisesRegex(ValueError,'file changed'):inspect_runtime(self.pack,verify=True)
        bulk.write_bytes(before);(self.pack/'unlisted.py').write_bytes(b'fixture')
        with self.assertRaisesRegex(ValueError,'Unlisted'):inspect_runtime(self.pack,verify=True)

    def test_saved_manifest_binding_is_enforced(self):
        expected=inspect_runtime(self.pack)['manifest_sha256']
        self.change(lambda v:v['abi'].update(torch='2.9.2+cpu'))
        with self.assertRaisesRegex(ValueError,'inventory changed'):inspect_runtime(self.pack,expected=expected)

    def test_external_pth_paths_and_hardlinks_are_rejected(self):
        (self.pack/'python311._pth').write_text('C:/outside\nimport site\n');seal(self.pack)
        with self.assertRaisesRegex(ValueError,'module paths'):inspect_runtime(self.pack)
        (self.pack/'python311._pth').write_text('python311.zip\n.\nDLLs\nLib/site-packages\nimport site\n');seal(self.pack)
        os.link(self.pack/'python.exe',self.base/'alias')
        with self.assertRaisesRegex(ValueError,'Hardlinked'):inspect_runtime(self.pack)

    def test_cancel_full_validation(self):
        with self.assertRaisesRegex(RuntimeError,'cancelled'):inspect_runtime(self.pack,verify=True,cancelled=lambda:True)

    def test_standalone_worker_uses_current_script_and_isolated_python(self):
        script=self.base/'worker.py';script.write_text('raise AssertionError("not executed")')
        command=worker_command(self.pack/'python.exe',script,['--model','fixture'])
        self.assertIn('-I',command);self.assertIn('-c',command)
        self.assertEqual(command[-3:],[str(script),'--model','fixture'])
        self.assertEqual(len(_verified_packs),1)

    def test_pack_is_fully_verified_once_but_core_and_binding_each_spawn(self):
        import ai_runtime
        script=self.base/'worker.py';script.write_bytes(b'fixture')
        info=inspect_runtime(self.pack);bind_runtime(self.pack,info['manifest_sha256'])
        with patch('ai_runtime.inspect_runtime',wraps=ai_runtime.inspect_runtime) as check:
            worker_command(self.pack/'python.exe',script,[]);worker_command(self.pack/'python.exe',script,[])
        self.assertEqual(sum(call.kwargs.get('verify',False) for call in check.call_args_list),1)
        self.change(lambda v:v['abi'].update(torch='2.9.2+cpu'))
        with self.assertRaisesRegex(ValueError,'inventory changed'):worker_command(self.pack/'python.exe',script,[])

    def test_selected_pack_cannot_skip_validation_by_removing_marker(self):
        info=inspect_runtime(self.pack);bind_runtime(self.pack,info['manifest_sha256'])
        script=self.base/'worker.py';script.write_text('fixture')
        (self.pack/MARKER).unlink()
        with self.assertRaises(ValueError):worker_command(self.pack/'python.exe',script,[])

    def test_legacy_venv_command_is_unchanged(self):
        script=self.base/'worker.py';script.write_bytes(b'fixture')
        command=worker_command(sys.executable,script,['--model','fixture'])
        self.assertEqual(command,[sys.executable,'-X','utf8','-B','-u',str(script),'--model','fixture'])

    def test_prepare_new_pack_never_changes_source_or_downloads(self):
        source=fixture(self.base/'source',source=True)
        (source/'python311._pth').write_text('python311.zip\n.\n../../backend/app\nimport site\n')
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()}
        output=self.base/'new pack'
        with patch('subprocess.Popen',side_effect=AssertionError('No process')):
            self.assertFalse(prepare(source,output,check=True)['prepared']);self.assertFalse(output.exists())
            result=prepare(source,output)
        self.assertTrue(result['prepared']);self.assertFalse(result['downloads'])
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in source.rglob('*') if p.is_file()})
        with self.assertRaises(FileExistsError):prepare(source,output)

    def test_duplicate_json_fields_are_rejected(self):
        path=self.pack/MARKER;path.write_text('{"format":"x","format":"y"}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):inspect_runtime(self.pack)

    def test_runtime_verification_status_progress_and_slow_flag(self):
        import ai_runtime
        import runtime_paths
        py=self.pack/'python.exe'
        initial=runtime_verification_status(py)
        self.assertEqual(initial['state'],'idle')
        self.assertFalse(initial['slow'])
        entered=threading.Event()
        release=threading.Event()
        observed=[]
        orig_inspect=ai_runtime.inspect_runtime
        def slow_inspect(root,*,verify=False,expected=None,cancelled=lambda:False,progress=None):
            if verify:
                def wrapped_progress(counts):
                    if progress is not None:progress(counts)
                    if counts.get('files_done',0)==1 and not entered.is_set():
                        entered.set()
                        release.wait(timeout=5)
                    observed.append(runtime_verification_status(py))
                return orig_inspect(root,verify=True,expected=expected,cancelled=cancelled,progress=wrapped_progress)
            return orig_inspect(root,verify=False,expected=expected,cancelled=cancelled,progress=progress)
        with patch('ai_runtime.inspect_runtime',side_effect=slow_inspect):
            self.assertTrue(start_runtime_verification(py))
            self.assertTrue(entered.wait(timeout=5))
            mid=runtime_verification_status(py)
            self.assertEqual(mid['state'],'verifying')
            self.assertGreater(mid['files_total'],0)
            self.assertGreater(mid['bytes_total'],0)
            self.assertGreater(mid['bytes_done'],0)
            self.assertFalse(mid['slow'])
            root_key=runtime_paths._root_key(self.pack)
            with runtime_paths._state_lock:
                runtime_paths._verify_state[root_key]['started_at']-=305.0
            slow_snap=runtime_verification_status(py)
            self.assertEqual(slow_snap['state'],'verifying')
            self.assertTrue(slow_snap['slow'])
            self.assertGreaterEqual(slow_snap['elapsed_seconds'],300.0)
            # A concurrent worker_command waits for in-progress verification instead of running a second full pass.
            script=self.base/'worker.py';script.write_bytes(b'fixture')
            cmd_done=threading.Event()
            def call_worker():
                worker_command(py,script,[])
                cmd_done.set()
            t=threading.Thread(target=call_worker,daemon=True)
            t.start()
            release.set()
            self.assertTrue(cmd_done.wait(timeout=5))
        final=runtime_verification_status(py)
        self.assertEqual(final['state'],'verified')
        self.assertEqual(final['files_done'],final['files_total'])
        self.assertEqual(final['bytes_done'],final['bytes_total'])
        self.assertFalse(final['slow'])
        self.assertFalse(start_runtime_verification(py))


class RuntimePreferencesTests(unittest.TestCase):
    def setUp(self):
        RuntimeContractTests.setUp(self)
        self.path=self.base/'settings/launch-settings.json'
        self.models=self.base/'models';self.models.mkdir()
        self.controller=AIRuntimePreferences(self.path,self.base,DEFAULT_PROFILE,
            active_python=sys.executable,active_models_root=self.base/'old models')

    def test_preferences_preserve_unrelated_fields_and_apply_on_restart(self):
        self.path.parent.mkdir();old={'database':str(self.base/'catalog.sqlite'),'ui_theme':'dark','ai_python':sys.executable}
        self.path.write_text(json.dumps(old));self.controller=AIRuntimePreferences(self.path,self.base,DEFAULT_PROFILE,active_python=sys.executable)
        state=self.controller.select(runtime_root=str(self.pack),models_root=str(self.models),consent=True)
        saved=read_preferences(self.path);validate_settings(saved)
        self.assertEqual(saved['database'],old['database']);self.assertEqual(saved['ui_theme'],'dark')
        self.assertNotIn('ai_python',saved);self.assertTrue(state['restart_required'])
        self.assertEqual(state['runtime']['state'],'pack_files_present');self.assertEqual(state['model']['state'],'model_missing')
        self.assertEqual(runtime_python(saved,'default','missing'),self.pack/'python.exe')

    def test_invalid_runtime_or_cancel_never_overwrites_settings(self):
        self.path.parent.mkdir();self.path.write_text('{"ui_theme":"light"}');before=self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            self.controller.select(runtime_root=str(self.pack),consent=True,cancelled=lambda:True)
        self.assertEqual(self.path.read_bytes(),before)
        (self.pack/'python.exe').write_bytes(b'bad')
        with self.assertRaises(ValueError):self.controller.select(runtime_root=str(self.pack),consent=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_no_consent_and_relative_folders_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'consent'):self.controller.select(runtime_root=str(self.pack))
        with self.assertRaisesRegex(ValueError,'absolute'):self.controller.select(models_root='relative',consent=True)
        self.assertFalse(self.path.exists())

    def test_models_and_runtime_can_be_selected_independently_and_reset(self):
        self.controller.select(models_root=str(self.models),consent=True)
        self.assertEqual(read_preferences(self.path),{'models_root':str(self.models)})
        self.controller.select(runtime_root=str(self.pack),consent=True)
        self.assertEqual(read_preferences(self.path)['models_root'],str(self.models))
        self.controller.select(runtime_root=None,models_root=None,consent=True)
        self.assertEqual(read_preferences(self.path),{})

    def test_broken_pack_disables_only_ai_resolution_not_basic_startup(self):
        self.controller.select(runtime_root=str(self.pack),consent=True)
        saved=read_preferences(self.path);(self.pack/'python.exe').write_bytes(b'bad')
        self.assertEqual(runtime_python(saved,'basic','not-installed'),Path('not-installed'))
        self.assertEqual(self.controller.snapshot()['runtime']['state'],'runtime_invalid')
        self.assertEqual(runtime_python({**saved,'ai_python':sys.executable},'basic','missing'),Path(sys.executable))

    def test_malformed_preferences_are_visible_not_an_exception(self):
        self.path.parent.mkdir();self.path.write_text('{"models_root":[]}')
        self.assertEqual(self.controller.snapshot()['runtime']['state'],'preferences_invalid')

    def test_model_revision_and_files_are_separate_from_runtime(self):
        directory=self.models/DEFAULT_PROFILE.directory;directory.mkdir()
        self.assertEqual(model_state(DEFAULT_PROFILE,self.base,self.models)['state'],'model_revision_missing')
        (directory/'aredoko-revision.txt').write_text('wrong')
        self.assertEqual(model_state(DEFAULT_PROFILE,self.base,self.models)['state'],'model_revision_mismatch')
        (directory/'aredoko-revision.txt').write_text(DEFAULT_PROFILE.revision)
        self.assertEqual(model_state(DEFAULT_PROFILE,self.base,self.models)['state'],'model_files_missing')
        for name in ('config.json','model.safetensors','tokenizer.json'):(directory/name).write_bytes(b'fixture')
        result=model_state(DEFAULT_PROFILE,self.base,self.models)
        self.assertEqual(result['state'],'model_files_present');self.assertFalse(result['model_loaded'])

    def test_basic_python_does_not_count_as_installed_ai_libraries(self):
        basic=self.base/'basic';basic.mkdir();(basic/'python.exe').write_bytes(b'fixture')
        self.assertEqual(legacy_runtime_state(basic/'python.exe'),'ai_libraries_missing')

    def test_cli_save_and_read_only_diagnostics(self):
        command=[sys.executable,'-B',str(ROOT/'tools/configure_ai_locations.py'),'--settings',str(self.path)]
        result=subprocess.run(command+['--runtime-root',str(self.pack),'--models-root',str(self.models),'--consent'],
            capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
        self.assertEqual(json.loads(result.stdout)['runtime']['state'],'pack_files_present')
        before=self.path.read_bytes(),self.path.stat().st_mtime_ns
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=20,check=True)
        self.assertFalse(json.loads(result.stdout)['inference_verified'])
        self.assertEqual(before,(self.path.read_bytes(),self.path.stat().st_mtime_ns))

    @unittest.skipUnless(os.name=='nt','Windows launch entry')
    def test_explicit_launch_settings_path_reaches_backend(self):
        import launch_release
        selected=self.base/'explicit.json';selected.write_text('{}')
        with patch.object(launch_release.sys,'argv',['launch_release.py','--settings',str(selected),'--no-error-dialog']), \
             patch.dict(os.environ,{'LOCALAPPDATA':str(self.base)}), \
             patch.object(launch_release,'launch') as launch:
            self.assertEqual(launch_release.main(),0)
        self.assertEqual(launch.call_args.kwargs['preferences_path'],selected.absolute())

    def test_launch_runtime_fields_are_paired_and_bounded(self):
        for data in ({'ai_runtime_root':str(self.pack)},{'ai_runtime_manifest_sha256':'a'*64},
                     {'ai_runtime_root':str(self.pack),'ai_runtime_manifest_sha256':'invalid'}):
            with self.assertRaises(ValueError):validate_settings(data)


class SetupHttpTests(unittest.TestCase):
    def test_setup_diagnostics_require_session_and_do_not_run_inference(self):
        from production import ProductionCatalog
        from production_server import production_handler,DisabledAI
        from ai_settings import AIProfileSettings
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);catalog=ProductionCatalog(base/'catalog.sqlite')
            profiles=AIProfileSettings(base,base/'settings.json',profile_directory=base/'profiles')
            server=ThreadingHTTPServer(('127.0.0.1',0),production_handler(catalog,'fixture-token',DisabledAI(),profiles=profiles))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                route=f'http://127.0.0.1:{server.server_port}/api/library/ai/setup'
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with self.assertRaises(urllib.error.HTTPError) as denied:opener.open(route)
                denied.exception.close();self.assertEqual(denied.exception.code,403)
                req=urllib.request.Request(route,headers={'X-Aredoko-Token':'fixture-token'})
                with opener.open(req) as response:value=json.load(response)
                self.assertFalse(value['inference_verified']);self.assertFalse(value['downloads_supported'])
                self.assertIn('runtime',value);self.assertIn('model',value)
            finally:server.shutdown();server.server_close();thread.join(timeout=2);catalog.close()


if __name__=='__main__':unittest.main()
