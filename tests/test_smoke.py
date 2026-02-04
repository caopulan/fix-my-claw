import tempfile
import unittest
from pathlib import Path

from fix_my_claw.config import load_config
from fix_my_claw.proc import run_cmd
from fix_my_claw.repair import _load_prompt_text
from fix_my_claw.util import redact_text


class TestSmoke(unittest.TestCase):
    def test_load_config_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing.toml"
            with self.assertRaises(FileNotFoundError):
                load_config(str(missing))

    def test_load_config_parses(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "cfg.toml"
            cfg_path.write_text(
                """
[monitor]
interval_seconds = 5
state_dir = "./state"

[openclaw]
command = "openclaw"
workspace_dir = "./ws"
state_dir = "./oc"
""".strip(),
                encoding="utf-8",
            )
            cfg = load_config(str(cfg_path))
            self.assertEqual(cfg.monitor.interval_seconds, 5)
            self.assertTrue(cfg.monitor.state_dir.is_absolute())
            self.assertTrue(cfg.openclaw.workspace_dir.is_absolute())

    def test_run_cmd_not_found(self) -> None:
        res = run_cmd(["__definitely_missing_cmd__"], timeout_seconds=1)
        self.assertEqual(res.exit_code, 127)

    def test_prompts_packaged(self) -> None:
        self.assertIn("OpenClaw", _load_prompt_text("repair.md"))

    def test_redact_text(self) -> None:
        s = "token=abc123 Authorization: Bearer xyz sk-abcdef0123456789"
        r = redact_text(s)
        self.assertNotIn("abc123", r)
        self.assertNotIn("xyz", r)
        self.assertNotIn("sk-abcdef0123456789", r)


if __name__ == "__main__":
    unittest.main()

