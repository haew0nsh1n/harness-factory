from test_package import PackageCase
from harness_factory.errors import HarnessError
from unittest.mock import patch
import json
import subprocess
import sys

from harness_factory.install import plan_install, apply_install


class InstallTests(PackageCase):
    def setUp(self):
        super().setUp()
        self.target = self.work / "target"

    def preview(self):
        return plan_install(self.package, self.target)

    def test_preview_no_mutation_apply_current_digest_preserves_unrelated(self):
        self.generate()
        self.target.mkdir()
        (self.target / "existing.txt").write_text("untouched")
        preview = self.preview()
        self.assertEqual(set(preview), {"ok", "operation", "package", "target", "digest", "files"})
        self.assertEqual(len(preview["digest"]), 64)
        self.assertFalse((self.target / ".agents").exists())
        result = apply_install(self.package, self.target, preview["digest"])
        self.assertTrue(result["ok"])
        self.assertEqual((self.target / "existing.txt").read_text(), "untouched")
        self.assertTrue((self.target / ".agents/skills/worker/SKILL.md").exists())
        from harness_factory.package import check_package
        self.assertTrue(check_package(self.target)["ok"])

    def test_stale_digest_and_no_digest_do_not_overwrite(self):
        self.generate()
        preview = self.preview()
        self.target.mkdir()
        (self.target / "INSTALL.md").write_text("changed touched state")
        for digest in [None, preview["digest"], "0" * 64]:
            with self.subTest(digest=digest), self.assertRaises(HarnessError):
                apply_install(self.package, self.target, digest)
        self.assertFalse((self.target / ".agents").exists())

    def test_overlap_directory_collision_and_symlink_ancestors(self):
        self.generate()
        for target in [self.package, self.package / "child", self.work]:
            with self.subTest(target=target), self.assertRaises(HarnessError):
                plan_install(self.package, target)
        self.target.mkdir()
        (self.target / ".agents").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(HarnessError):
            self.preview()
        (self.target / ".agents").unlink()
        (self.target / ".harness/manifest.json").mkdir(parents=True)
        with self.assertRaises(HarnessError):
            self.preview()

    def test_source_changed_after_preview(self):
        self.generate()
        preview = self.preview()
        (self.package / ".agents/skills/worker/SKILL.md").write_text("tampered")
        with self.assertRaises(HarnessError):
            apply_install(self.package, self.target, preview["digest"])
        self.assertFalse(self.target.exists())

    def test_existing_symlink_file_never_overwritten(self):
        self.generate()
        (self.target / ".harness").mkdir(parents=True)
        (self.target / ".harness/customer.json").symlink_to(self.root / "license.txt")
        with self.assertRaises(HarnessError):
            self.preview()

    def test_partial_write_failure_is_explicit_and_not_false_rollback(self):
        import os
        self.generate()
        preview = self.preview()
        replace = os.replace
        calls = []
        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError("disk full")
            return replace(source, target)
        with patch("os.replace", side_effect=fail_second), self.assertRaisesRegex(
                HarnessError, "partial install.*no rollback.*1 files written"):
            apply_install(self.package, self.target, preview["digest"])
        self.assertTrue(self.target.exists())
        self.assertFalse(list(self.target.rglob(".hf-write-*")))

    def test_target_path_and_same_content_directory_state_bind_approval(self):
        self.generate()
        preview = self.preview()
        with self.assertRaises(HarnessError):
            apply_install(self.package, self.work / "other-target", preview["digest"])
        self.target.mkdir()
        preview = self.preview()
        (self.target / ".harness/empty-directory").mkdir(parents=True)
        with self.assertRaises(HarnessError):
            apply_install(self.package, self.target, preview["digest"])

    def test_active_customer_repository_changes_do_not_invalidate_installed_receipt(self):
        from harness_factory.package import check_package
        self.generate()
        self.target.mkdir()
        (self.target / "src").mkdir()
        (self.target / "src/customer.py").write_text("value = 1\n")
        (self.target / "README.md").write_text("Customer project\n")
        (self.target / "INSTALL.md").write_text("Existing customer install instructions\n")
        other_skill = self.target / ".agents/skills/customer-owned/SKILL.md"
        other_skill.parent.mkdir(parents=True)
        other_skill.write_text("Customer-owned skill\n")
        def git(*args):
            result = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
                 "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
                cwd=self.target, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        git("-c", "init.templateDir=", "init", "--quiet")
        git("add", "src", "README.md")
        message = ("Fixture state\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>\n"
                   "Copilot-Session: d00fa887-0caf-42f6-82c2-cf960d308b94")
        git("commit", "--quiet", "-m", message)
        preview = self.preview()
        self.assertIn({"path": "INSTALL.md", "action": "replace"}, preview["files"])
        apply_install(self.package, self.target, preview["digest"])
        manifest = json.loads((self.target / ".harness/manifest.json").read_text())
        self.assertEqual(manifest.get("mode"), "installed")
        self.assertNotIn("src/customer.py", manifest["files"])
        self.assertNotIn("README.md", manifest["files"])
        (self.target / "src/customer.py").write_text("value = 2\n")
        (self.target / "src/new.py").write_text("new_value = 3\n")
        other_skill.write_text("Customer updates an unrelated skill\n")
        git("add", "src")
        git("commit", "--quiet", "-m", message)
        self.assertEqual((self.target / "README.md").read_text(), "Customer project\n")
        for args in [
            ["check", "--package", "."],
            ["preflight", "--package", "."],
            ["record", "--package", ".", "--run", "customer-change", "--step", "build", "--status", "running"],
            ["record", "--package", ".", "--run", "customer-change", "--step", "build", "--status", "completed",
             "--evidence", "Customer fixture source change and Git commit verified"],
        ]:
            result = subprocess.run([sys.executable, "-m", "harness_factory", *args], cwd=self.target,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["ok"])
        for relative in ["harness_factory/contracts.py", ".agents/skills/worker/SKILL.md"]:
            path = self.target / relative
            original = path.read_bytes()
            path.write_bytes(original + b"\n# changed\n")
            with self.subTest(tamper=relative), self.assertRaises(HarnessError):
                check_package(self.target)
            path.write_bytes(original)
        (self.target / "harness_factory/extra.py").write_text("# Unlisted managed payload\n")
        with self.assertRaisesRegex(HarnessError, "unlisted"):
            check_package(self.target)

    def test_installed_receipt_cannot_be_used_as_distribution_source(self):
        self.generate()
        apply_install(self.package, self.target, self.preview()["digest"])
        with self.assertRaisesRegex(HarnessError, "distribution"):
            plan_install(self.target, self.work / "second")

    def test_unrelated_edits_do_not_stale_preview_or_reject_customer_symlinks(self):
        from harness_factory.package import check_package
        self.generate()
        self.target.mkdir()
        (self.target / "customer.txt").write_text("before")
        (self.target / "customer-link").symlink_to(self.target / "customer.txt")
        preview = self.preview()
        (self.target / "customer.txt").write_text("after")
        (self.target / "new-source.py").write_text("value = 1\n")
        apply_install(self.package, self.target, preview["digest"])
        self.assertTrue(check_package(self.target)["ok"])

    def test_unmanaged_file_inside_newly_owned_root_is_explicit_collision(self):
        self.generate()
        (self.target / "harness_factory").mkdir(parents=True)
        (self.target / "harness_factory/customer.py").write_text("customer = True\n")
        with self.assertRaisesRegex(HarnessError, "owned|unlisted|collision"):
            self.preview()
        self.assertFalse((self.target / ".harness").exists())

    def test_repeat_install_preview_compares_installed_receipt_bytes(self):
        self.generate()
        apply_install(self.package, self.target, self.preview()["digest"])
        preview = self.preview()
        self.assertTrue(all(item["action"] == "unchanged" for item in preview["files"]), preview["files"])
        self.assertEqual(apply_install(self.package, self.target, preview["digest"])["written"], [])

    def test_customer_gitignore_is_never_replaced(self):
        self.generate()
        self.target.mkdir()
        original = b"build/\ncustomer-private/\n"
        (self.target / ".gitignore").write_bytes(original)
        preview = self.preview()
        self.assertNotIn(".gitignore", [item["path"] for item in preview["files"]])
        apply_install(self.package, self.target, preview["digest"])
        self.assertEqual((self.target / ".gitignore").read_bytes(), original)
