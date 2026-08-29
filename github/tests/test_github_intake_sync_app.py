from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import github_intake_sync_app as sync_app


class GitHubIntakeSyncAppTests(unittest.TestCase):
    def test_missing_identity_is_a_successful_noop_for_the_cooldown_order(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["github_intake_sync_app.py", "--quiet"]), mock.patch.object(
            sync_app.service,
            "sync_github_app_config_from_identity",
            return_value={"status": "skipped", "reason": "GITHUB_INTAKE_APP_IDENTITY is not configured"},
        ):
            with contextlib.redirect_stderr(stderr):
                exit_code = sync_app.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
