"""설치/모델 호출 없이 Codex·Node 경로 복구와 사전 점검을 검증한다."""
import argparse
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import orchestrator as loop


class AgentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.nvm=self.root/'nvm'

    def executable(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755)
        return path

    def node_install(self,version):
        folder=self.nvm/'versions/node'/version/'bin'
        for name in ('codex','node'):self.executable(folder/name)
        return folder

    def test_missing_path_uses_installed_node_pair(self):
        folder=self.node_install('v22.22.2')
        env={'PATH':'/nonexistent','NVM_DIR':str(self.nvm)}
        with patch.dict(os.environ,env,clear=True):
            child=loop.agent_env('0,1')
            self.assertEqual(os.environ['PATH'],'/nonexistent')
        self.assertEqual(child['PATH'].split(os.pathsep)[:2],[str(loop.CONDA_ENV/'bin'),str(folder)])
        self.assertEqual(child['CUDA_VISIBLE_DEVICES'],'0,1')

    def test_existing_codex_not_replaced_by_another_install(self):
        chosen=self.root/'custom';self.executable(chosen/'codex')
        self.node_install('v99.0.0')
        self.assertIsNone(loop.agent_node_bin({'PATH':str(chosen),'NVM_DIR':str(self.nvm)}))

    def test_existing_npm_launcher_uses_sibling_node(self):
        folder=self.node_install('v22.22.2')
        self.assertEqual(loop.agent_node_bin({'PATH':str(folder)}),folder)

    def test_nvm_bin_preferred_to_version_scan(self):
        older=self.node_install('v22.0.0');self.node_install('v24.0.0')
        self.assertEqual(loop.agent_node_bin({'PATH':'/nonexistent','NVM_BIN':str(older),'NVM_DIR':str(self.nvm)}),older)

    def test_no_install_preserves_missing_state(self):
        self.assertIsNone(loop.agent_node_bin({'PATH':'/nonexistent','NVM_DIR':str(self.nvm)}))

    def test_preflight_does_not_invoke_model(self):
        with patch.object(loop,'agent_env',return_value={'PATH':'/test'}),patch.object(loop.shutil,'which',return_value='/test/codex'),patch.object(loop.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='codex-cli test',stderr='')) as run:
            loop.validate_codex_runtime(argparse.Namespace(gpus=None))
            self.assertEqual(run.call_args.args[0],['/test/codex','--version'])

    def test_broken_node_detected_before_loop(self):
        with patch.object(loop,'agent_env',return_value={'PATH':'/test'}),patch.object(loop.shutil,'which',return_value='/test/codex'),patch.object(loop.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='',stderr='SyntaxError')):
            with self.assertRaisesRegex(loop.AgentError,'사전 점검 실패'):
                loop.validate_codex_runtime(argparse.Namespace(gpus=None))


if __name__=='__main__':unittest.main()
