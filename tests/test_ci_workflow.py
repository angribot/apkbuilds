"""Publication-contract tests for .github/workflows/ci.yml.

These tests cover fail-open mistakes that shell syntax checks cannot detect.
Real APK parsing, installation, and signing remain integration checks in CI.
"""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
MERGER_PATH = ROOT / "scripts" / "merge-package-families.sh"
MERGER = MERGER_PATH.read_text()


class PackageOriginBuildTest(unittest.TestCase):
    def test_build_uses_complete_declared_and_published_families(self):
        self.assertIn("abuild listpkg", WORKFLOW)
        self.assertIn("apkindex_origin_apks", WORKFLOW)
        self.assertIn("package_sets_equal", WORKFLOW)
        self.assertIn("apkindex_origin_versions", WORKFLOW)
        self.assertNotIn("apkbuild_pinned_apk", WORKFLOW)

    def test_exact_published_family_is_verified_before_skip(self):
        comparison = WORKFLOW.index('package_sets_equal "$expected" "$published"')
        skip = WORKFLOW.index("package family already published", comparison)
        physical_verification = WORKFLOW.index('apk verify "$downloaded"', comparison)
        self.assertLess(comparison, physical_verification)
        self.assertLess(physical_verification, skip)

    def test_each_candidate_family_has_isolated_artifact_directory(self):
        self.assertIn('/new/$origin/packages/$ARCH', WORKFLOW)
        self.assertIn('/new/built/$ARCH/$origin', WORKFLOW)
        self.assertIn("path: ${{ runner.temp }}/new/built/", WORKFLOW)
        self.assertIn("merge-multiple: true", WORKFLOW)
        self.assertIn('source="$built/$arch"', MERGER)


class PackageOriginReplacementTest(unittest.TestCase):
    def test_workflow_runs_merger_without_network_access(self):
        merge_step = WORKFLOW.index("- name: Validate and merge candidate package families")
        signing_step = WORKFLOW.index(
            "- name: Sign the APK repository without network access", merge_step
        )
        merge_workflow = WORKFLOW[merge_step:signing_step]
        self.assertIn("docker run --rm --network none", merge_workflow)
        self.assertIn("/workspace/scripts/merge-package-families.sh", merge_workflow)

    def test_merger_is_valid_shell(self):
        completed = subprocess.run(
            ["sh", "-n", str(MERGER_PATH)], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_candidate_is_validated_before_published_family_is_removed(self):
        validation = MERGER.index("apkindex_validate_family")
        removal = MERGER.index('rm -f "$apk_repository/$package"')
        copying = MERGER.index('cp "$candidate" "$apk_repository/"')
        self.assertLess(validation, removal)
        self.assertLess(removal, copying)

    def test_published_family_comes_from_verified_index(self):
        verification = MERGER.index('apk verify "$apk_repository/APKINDEX.tar.gz"')
        extraction = MERGER.index("APKINDEX.tar.gz\" APKINDEX", verification)
        family_lookup = MERGER.index("apkindex_origin_apks", extraction)
        self.assertLess(verification, extraction)
        self.assertLess(extraction, family_lookup)

    def test_unsupported_architecture_has_no_replacement_candidate(self):
        support_check = WORKFLOW.index('supports_arch "$ARCH"')
        candidate_directory = WORKFLOW.index('/new/built/$ARCH/$origin')
        self.assertLess(support_check, candidate_directory)
        self.assertIn('supports_arch "$ARCH" "packages/$origin/APKBUILD" || continue', WORKFLOW)

    def test_every_architecture_baseline_is_verified_during_publication(self):
        source_guard = MERGER.index('if ! test -d "$source"')
        baseline_verification = MERGER.index(
            'apk verify "$apk_repository/APKINDEX.tar.gz"'
        )
        self.assertLess(baseline_verification, source_guard)

    def test_final_signed_snapshot_matches_its_physical_apks(self):
        verification_step = WORKFLOW.index(
            "- name: Verify the APK repository without the private key"
        )
        verification_script = WORKFLOW[verification_step:]
        self.assertIn("apkindex_apks", verification_script)
        self.assertIn("package_sets_equal", verification_script)

    def test_staged_snapshot_is_installed_before_publication(self):
        verify_job = WORKFLOW.index("\n  verify:")
        publish_job = WORKFLOW.index("\n  publish:")
        self.assertLess(verify_job, publish_job)
        self.assertIn("verify:\n    needs: sign", WORKFLOW)
        self.assertIn("publish:\n    needs: verify", WORKFLOW)
        self.assertIn("snapshot_created: ${{ steps.merge.outputs.merged }}", WORKFLOW)
        staged_verification = WORKFLOW[verify_job:publish_job]
        self.assertIn("if: needs.sign.outputs.snapshot_created == 'true'", staged_verification)
        self.assertNotIn("continue-on-error", staged_verification)
        self.assertIn('echo "/pages/edge"', staged_verification)
        self.assertNotIn("PAGES_URL", staged_verification)


if __name__ == "__main__":
    unittest.main()
