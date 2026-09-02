from __future__ import annotations

import io
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_docs_bootstrap_commands as commands


class DocsBootstrapCommandsTests(unittest.TestCase):
    @mock.patch.object(commands, "project_configured_root")
    def test_project_once_invokes_authenticated_durable_projection_caller(self, project: mock.Mock) -> None:
        project.return_value = {"identity": "bootstrap-1", "actions": []}
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", [
            "github_intake_docs_bootstrap_commands.py", "project", "--once",
            "--store", "/state/docs-bootstrap", "--identity", "bootstrap-1",
        ]), mock.patch.object(sys, "stdout", stdout):
            self.assertEqual(commands.main(), 0)

        project.assert_called_once_with("/state/docs-bootstrap", "bootstrap-1")
        self.assertIn('"identity":"bootstrap-1"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
