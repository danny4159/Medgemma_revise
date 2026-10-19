"""승인된 외부 데이터 경로가 실제 Claude 신규/재개 명령에 전달되는지 검사한다."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrator as loop


class ExternalPathTests(unittest.TestCase):
    def test_new_and_resumed_command_use_configured_scoped_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'mri'
            data.mkdir()
            (root / 'claude_settings.json').write_text(json.dumps({
                'permissions': {'additionalDirectories': [str(data), str(data)]}}))
            with patch.object(loop, 'AGENT_DIR', root):
                for session in (None, 'saved-session'):
                    cmd = loop.claude_command('standard', session)
                    start = cmd.index('--add-dir') + 1
                    end = cmd.index('--append-system-prompt-file')
                    self.assertEqual(cmd[start:end], [str(loop.PROJECT_DIR), str(data)])
                    self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'acceptEdits')
                    self.assertNotIn('--dangerously-skip-permissions', cmd)
                    if session:
                        self.assertEqual(cmd[cmd.index('--resume') + 1], session)

    def test_invalid_and_broad_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(loop, 'AGENT_DIR', root):
                for values in (['/'], [str(Path.home())], ['relative'], ['/missing-mrrate-dir'], 'not-list'):
                    (root / 'claude_settings.json').write_text(json.dumps({
                        'permissions': {'additionalDirectories': values}}))
                    with self.assertRaises(loop.AgentError):
                        loop.claude_working_directories()

    def test_production_path_and_protection_rules(self):
        settings = loop.load_json(loop.AGENT_DIR / 'claude_settings.json')
        self.assertEqual(settings['permissions']['additionalDirectories'],
                         ['/home/test/.local/share/medgemma/mr_rate'])
        deny = settings['permissions']['deny']
        for rule in ('Bash(sudo *)', 'Bash(rm *)', 'Bash(git push *)',
                     'Write(//SSD1_1TB/home/milab/daniel/08_medgemma/hf_cache/**)'):
            self.assertIn(rule, deny)


if __name__ == '__main__':
    unittest.main()
