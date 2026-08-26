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
    def test_manual_dispatch_plans_the_selected_revision(self):
        self.assertIn("revision:", WORKFLOW)
        self.assertIn("base_revision:", WORKFLOW)
        self.assertEqual(WORKFLOW.count("ref: ${{ inputs.revision || github.sha }}"), 5)
        plan = WORKFLOW[WORKFLOW.index("  plan:") : WORKFLOW.index("\n  build:")]
        self.assertIn("REVISION: ${{ inputs.revision || github.sha }}", plan)
        self.assertIn("BASE_REVISION: ${{ inputs.base_revision }}", plan)
        self.assertIn(
            "EXPLICIT_REVISION: ${{ inputs.revision != '' && 'true' || 'false' }}",
            plan,
        )
        self.assertIn(
            "MAIN_REVISION: origin/${{ github.event.repository.default_branch }}",
            plan,
        )
        self.assertIn("run: sh scripts/plan-origins.sh", plan)

    def test_full_dispatch_still_plans_all_origins(self):
        plan = WORKFLOW[WORKFLOW.index("  plan:") : WORKFLOW.index("\n  build:")]
        self.assertIn("FULL: ${{ inputs.full || 'false' }}", plan)
        self.assertIn("run: sh scripts/plan-origins.sh", plan)

    def test_package_origin_inputs_require_declared_build_increase(self):
        guard_start = WORKFLOW.index("- name: Require a version increase")
        guard = WORKFLOW[guard_start : WORKFLOW.index("\n\n  plan:", guard_start)]
        self.assertIn("run: sh scripts/check-package-versions.sh", guard)
        self.assertIn(
            'git diff --quiet "$BASE_SHA" -- "packages/$origin"',
            (ROOT / "scripts" / "check-package-versions.sh").read_text(),
        )
        self.assertIn(
            'git show "$BASE_SHA:$apkbuild"',
            (ROOT / "scripts" / "check-package-versions.sh").read_text(),
        )
        self.assertNotIn(
            'git diff --quiet "$BASE_SHA" -- "$apkbuild"',
            (ROOT / "scripts" / "check-package-versions.sh").read_text(),
        )

    def test_plan_runs_in_parallel_with_repository_checks(self):
        plan_start = WORKFLOW.index("  plan:")
        build_start = WORKFLOW.index("\n  build:", plan_start)
        plan = WORKFLOW[plan_start:build_start]
        build = WORKFLOW[build_start : WORKFLOW.index("\n  sign:", build_start)]
        self.assertNotIn("needs:", plan)
        self.assertIn("needs: [check, plan]", build)

    def test_check_container_needs_no_bash_for_update_script_tests(self):
        install_step = WORKFLOW[WORKFLOW.index("- name: Install tools") :]
        install_step = install_step[: install_step.index("- uses: actions/checkout")]
        self.assertIn("apk add --no-cache", install_step)
        self.assertNotIn(" bash", install_step)

    def test_ccache_snapshots_use_unique_keys_with_compatible_fallback(self):
        key_start = WORKFLOW.index("- name: Compute ccache cache keys")
        restore_start = WORKFLOW.index("- name: Restore ccache", key_start)
        save_start = WORKFLOW.index("- name: Save ccache", restore_start)
        stage_start = WORKFLOW.index("- name: Stage", save_start)
        key_step = WORKFLOW[key_start:restore_start]
        restore = WORKFLOW[restore_start:save_start]
        save = WORKFLOW[save_start:stage_start]
        prefix = (
            "apkbuilds-ccache-${{ matrix.arch }}-${{ matrix.origin }}-"
            "${{ runner.os }}-"
        )
        unique_suffix = (
            "${{ hashFiles(format('packages/{0}/**', matrix.origin)) }}-"
            "${{ github.run_id }}-${{ github.run_attempt }}"
        )
        self.assertIn(f'echo "prefix={prefix}"', key_step)
        self.assertIn(f'echo "key={prefix}{unique_suffix}"', key_step)
        self.assertIn("key: ${{ steps.ccache-key.outputs.key }}", restore)
        self.assertIn("restore-keys: ${{ steps.ccache-key.outputs.prefix }}", restore)
        self.assertIn("key: ${{ steps.ccache-key.outputs.key }}", save)

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
        self.assertIn('/new/$ORIGIN/packages/$ARCH', WORKFLOW)
        self.assertIn('/new/built/$ARCH/$ORIGIN', WORKFLOW)
        self.assertIn("path: ${{ runner.temp }}/new/built/", WORKFLOW)
        self.assertIn("merge-multiple: true", WORKFLOW)
        self.assertIn('source="$built/$arch"', MERGER)

    def test_orbien_client_is_smoke_tested_after_install(self):
        installation = WORKFLOW.index('"$@"')
        smoke_test = WORKFLOW.index("scripts/test-orbien.sh", installation)
        staging = WORKFLOW.index('candidate="/new/built/$ARCH/$ORIGIN"', installation)
        self.assertLess(installation, smoke_test)
        self.assertLess(smoke_test, staging)


class PackageOriginReplacementTest(unittest.TestCase):
    def test_candidate_indexing_accepts_untrusted_signatures(self):
        # Candidates arrive signed with the ephemeral build key, which the
        # network-isolated signer must not trust. The candidate index serves
        # structural validation only; the repository signing key re-signs the
        # packages later, and the final verification step checks that key.
        candidate_index = MERGER.index("apk index --no-warnings --quiet")
        self.assertIn("--allow-untrusted", MERGER[candidate_index:])

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
        candidate_directory = WORKFLOW.index('/new/built/$ARCH/$ORIGIN')
        self.assertLess(support_check, candidate_directory)
        self.assertIn('supports_arch "$ARCH" "packages/$ORIGIN/APKBUILD" || exit 0', WORKFLOW)

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
