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
BUILD_MODULE = (ROOT / "scripts" / "build-package-family.sh").read_text()
VERIFY_MODULE = (ROOT / "scripts" / "verify-repository.sh").read_text()


class PackageOriginBuildTest(unittest.TestCase):
    def test_all_pull_request_changes_trigger_the_required_gate(self):
        triggers = WORKFLOW[: WORKFLOW.index("permissions:")]
        self.assertNotIn("paths-ignore:", triggers)
        self.assertNotIn("paths:", triggers)
        self.assertIn("push:\n    branches: [main]", triggers)
        self.assertIn("pull_request:\n", triggers)

    def test_manual_dispatch_plans_the_selected_revision(self):
        self.assertIn("revision:", WORKFLOW)
        self.assertIn("base_revision:", WORKFLOW)
        self.assertEqual(WORKFLOW.count("ref: ${{ inputs.revision || github.sha }}"), 4)
        check = WORKFLOW[WORKFLOW.index("  check:") : WORKFLOW.index("\n  build:")]
        self.assertIn("REVISION: ${{ inputs.revision || github.sha }}", check)
        self.assertIn("BASE_REVISION: ${{ inputs.base_revision }}", check)
        self.assertIn(
            "EXPLICIT_REVISION: ${{ inputs.revision != '' && 'true' || 'false' }}",
            check,
        )
        self.assertIn(
            "MAIN_REVISION: origin/${{ github.event.repository.default_branch }}",
            check,
        )
        self.assertIn("run: sh scripts/plan-origins.sh", check)
        self.assertNotIn("\n  plan:", WORKFLOW)

    def test_full_dispatch_still_plans_all_origins(self):
        check = WORKFLOW[WORKFLOW.index("  check:") : WORKFLOW.index("\n  build:")]
        self.assertIn("FULL: ${{ inputs.full || 'false' }}", check)
        self.assertIn("run: sh scripts/plan-origins.sh", check)

    def test_package_origin_inputs_require_declared_build_increase(self):
        guard_start = WORKFLOW.index("- name: Require a version increase")
        guard = WORKFLOW[guard_start : WORKFLOW.index("\n\n  build:", guard_start)]
        self.assertIn("run: sh scripts/check-declared-build.sh", guard)
        self.assertIn(
            'git diff --no-renames --name-only "$BASE_SHA" -- packages/',
            (ROOT / "scripts" / "check-declared-build.sh").read_text(),
        )
        self.assertIn(
            'git show "$BASE_SHA:$apkbuild"',
            (ROOT / "scripts" / "check-declared-build.sh").read_text(),
        )
        self.assertNotIn(
            'git diff --quiet "$BASE_SHA" -- "$apkbuild"',
            (ROOT / "scripts" / "check-declared-build.sh").read_text(),
        )

    def test_validation_and_planning_share_one_checkout_and_job(self):
        check_start = WORKFLOW.index("  check:")
        build_start = WORKFLOW.index("\n  build:", check_start)
        check = WORKFLOW[check_start:build_start]
        build = WORKFLOW[build_start : WORKFLOW.index("\n  sign:", build_start)]
        self.assertIn("outputs:", check)
        self.assertIn("matrix: ${{ steps.set-matrix.outputs.matrix }}", check)
        self.assertIn("has_origins: ${{ steps.set-matrix.outputs.has_origins }}", check)
        self.assertIn("reconcile: ${{ steps.set-matrix.outputs.reconcile }}", check)
        self.assertEqual(check.count("actions/checkout@"), 1)
        self.assertIn("needs: check", build)
        self.assertNotIn("needs: [check, plan]", build)

    def test_reconciliation_verifies_an_unchanged_published_snapshot(self):
        check_start = WORKFLOW.index("  check:")
        sign_start = WORKFLOW.index("\n  sign:")
        check = WORKFLOW[check_start:sign_start]
        sign = WORKFLOW[sign_start : WORKFLOW.index("\n  verify:", sign_start)]
        self.assertIn(
            "reconcile: ${{ steps.set-matrix.outputs.reconcile }}", check
        )
        self.assertIn("needs: [build, check]", sign)
        self.assertIn(
            "steps.merge.outputs.merged == 'true' ||\n          needs.check.outputs.reconcile == 'true'",
            sign,
        )
        self.assertNotIn("contents: write", sign)
        self.assertIn("id: snapshot", sign)
        self.assertIn("if: steps.snapshot.outputs.created == 'true'", sign)

    def test_build_mismatch_logs_source_and_build_identities(self):
        self.assertIn(
            '--source-revision "${{ inputs.revision || github.sha }}"', WORKFLOW
        )
        self.assertIn("source revision=", BUILD_MODULE)
        self.assertIn("declared build=", BUILD_MODULE)
        self.assertIn("published build(s)=", BUILD_MODULE)
        self.assertIn("package set mismatch:", BUILD_MODULE)

    def test_workflow_exposes_a_stable_branch_protection_gate(self):
        gate_start = WORKFLOW.index("\n  gate:")
        gate = WORKFLOW[gate_start:]
        self.assertIn(
            "needs: [check, build, sign, verify, publish]", gate
        )
        self.assertIn("EVENT: ${{ github.event_name }}", gate)
        self.assertIn("HAS_ORIGINS: ${{ needs.check.outputs.has_origins }}", gate)
        self.assertNotIn("needs.plan", gate)
        self.assertIn('test "$CHECK" = success', gate)
        self.assertIn('if [ "$HAS_ORIGINS" = true ]; then', gate)
        self.assertIn('test "$BUILD" = success', gate)
        self.assertIn('test "$PUBLISH" = success', gate)

    def test_publication_uses_an_explicit_deploy_key(self):
        publish_start = WORKFLOW.index("  publish:")
        publish = WORKFLOW[publish_start:]
        self.assertIn(
            "PAGES_DEPLOY_KEY: ${{ secrets.PAGES_DEPLOY_KEY }}", publish
        )
        self.assertIn('git remote add origin "git@github.com:$GITHUB_REPOSITORY.git"', publish)
        self.assertIn("git push -q --force origin gh-pages", publish)

    def test_check_container_needs_no_bash_for_update_script_tests(self):
        install_step = WORKFLOW[WORKFLOW.index("- name: Install tools") :]
        install_step = install_step[: install_step.index("- uses: actions/checkout")]
        self.assertIn("apk add --no-cache", install_step)
        self.assertNotIn(" bash", install_step)

    def test_build_container_cannot_change_checkout_ownership(self):
        build_start = WORKFLOW.index("  build:")
        sign_start = WORKFLOW.index("\n  sign:", build_start)
        build = WORKFLOW[build_start:sign_start]
        self.assertIn('-v "$GITHUB_WORKSPACE:/workspace:ro"', build)
        self.assertIn('build-package-family.sh', build)
        self.assertIn('cp -R "$workspace/packages/$origin" "$output/source/"', BUILD_MODULE)
        self.assertIn(
            'sh "$workspace/scripts/prepare-builder.sh" \\\n  "$output" "$distfiles" "$cargo_home" "$ccache_dir" "$sccache_dir"',
            BUILD_MODULE,
        )
        self.assertIn(
            'cd \\\"$output/source/$origin\\\" && CARGO_HOME=', BUILD_MODULE
        )
        self.assertIn('REPODEST=', BUILD_MODULE)
        self.assertNotIn("prepare-builder.sh /new /workspace", build)

    def test_builder_setup_documents_writable_directory_boundary(self):
        setup = (ROOT / "scripts" / "prepare-builder.sh").read_text()
        self.assertIn("writable directories", setup)
        self.assertIn('chown -R builder:builder "$directory"', setup)

    def test_ccache_snapshots_use_unique_keys_with_compatible_fallback(self):
        key_start = WORKFLOW.index("- name: Compute compiler cache keys")
        restore_start = WORKFLOW.index("- name: Restore compiler caches", key_start)
        stage_start = WORKFLOW.index("- name: Stage", restore_start)
        save_start = WORKFLOW.index("- name: Save compiler caches", stage_start)
        upload_start = WORKFLOW.index("- uses: actions/upload-artifact", save_start)
        key_step = WORKFLOW[key_start:restore_start]
        restore = WORKFLOW[restore_start:stage_start]
        save = WORKFLOW[save_start:upload_start]
        prefix = (
            "apkbuilds-ccache-${{ matrix.arch }}-${{ matrix.origin }}-"
            "${{ runner.os }}-${{ env.CI_TOOLCHAIN }}-"
        )
        unique_suffix = (
            "${{ hashFiles(format('packages/{0}/**', matrix.origin)) }}-"
            "${{ github.run_id }}-${{ github.run_attempt }}"
        )
        self.assertIn(f'echo "prefix={prefix}"', key_step)
        self.assertIn(f'echo "key={prefix}{unique_suffix}"', key_step)
        self.assertIn("key: ${{ steps.ccache-key.outputs.key }}", restore)
        self.assertIn("restore-keys: ${{ steps.ccache-key.outputs.prefix }}", restore)
        self.assertIn(".cache/cargo-${{ matrix.origin }}", restore)
        self.assertIn(".cache/sccache-${{ matrix.origin }}", restore)
        self.assertIn("CACHE_HIT: ${{ steps.ccache.outputs.cache-hit }}", WORKFLOW)
        self.assertIn(
            "CACHE_MATCHED_KEY: ${{ steps.ccache.outputs.cache-matched-key }}", WORKFLOW
        )
        self.assertIn("cache_restore_key=", WORKFLOW)
        self.assertIn("key: ${{ steps.ccache-key.outputs.key }}", save)
        self.assertIn(".cache/cargo-${{ matrix.origin }}", save)
        self.assertIn(".cache/sccache-${{ matrix.origin }}", save)
        self.assertIn("if: steps.stage.outputs.built == 'true'", save)

    def test_build_reports_compiler_cache_and_timing_metrics(self):
        self.assertIn("CI_TOOLCHAIN: alpine-edge-rust-v1", WORKFLOW)
        self.assertIn("RUSTC_WRAPPER=sccache", BUILD_MODULE)
        self.assertIn("ccache --show-stats", BUILD_MODULE)
        self.assertIn("sccache --show-stats", BUILD_MODULE)
        self.assertIn("build_seconds=", BUILD_MODULE)
        self.assertIn("du -sb", BUILD_MODULE)
        self.assertIn("GITHUB_STEP_SUMMARY", WORKFLOW)
        self.assertIn(
            "cargo build", (ROOT / "packages/orbien/APKBUILD").read_text()
        )

    def test_build_uses_complete_declared_and_published_families(self):
        self.assertIn("abuild listpkg", BUILD_MODULE)
        self.assertIn("apkindex_origin_apks", BUILD_MODULE)
        self.assertIn("package_sets_equal", BUILD_MODULE)
        self.assertIn("apkindex_origin_versions", BUILD_MODULE)
        self.assertNotIn("apkbuild_pinned_apk", BUILD_MODULE)

    def test_exact_published_family_is_verified_before_skip(self):
        comparison = BUILD_MODULE.index('package_sets_equal "$expected" "$published_packages"')
        skip = BUILD_MODULE.index("package family already published", comparison)
        physical_verification = BUILD_MODULE.index('apk verify "$downloaded"', comparison)
        self.assertLess(comparison, physical_verification)
        self.assertLess(physical_verification, skip)

    def test_each_candidate_family_has_isolated_artifact_directory(self):
        self.assertIn('$output/$origin/packages/$arch', BUILD_MODULE)
        self.assertIn('$output/built/$arch/$origin', BUILD_MODULE)
        self.assertIn("path: ${{ runner.temp }}/new/built/", WORKFLOW)
        self.assertIn("merge-multiple: true", WORKFLOW)
        self.assertIn('source="$built/$arch"', MERGER)

    def test_orbien_client_is_smoke_tested_after_install(self):
        installation = BUILD_MODULE.index('"$@"')
        smoke_test = BUILD_MODULE.index("test-orbien.sh", installation)
        staging = BUILD_MODULE.index('candidate="$output/built/$arch/$origin"', installation)
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
        support_check = BUILD_MODULE.index('supports_arch "$arch"')
        candidate_directory = BUILD_MODULE.index('/built/$arch/$origin')
        self.assertLess(support_check, candidate_directory)
        self.assertIn('supports_arch "$arch" "$workspace/packages/$origin/APKBUILD" || exit 0', BUILD_MODULE)

    def test_every_architecture_baseline_is_verified_during_publication(self):
        source_guard = MERGER.index('if ! test -d "$source"')
        baseline_verification = MERGER.index(
            'apk verify "$apk_repository/APKINDEX.tar.gz"'
        )
        self.assertLess(baseline_verification, source_guard)

    def test_final_signed_snapshot_matches_its_physical_apks(self):
        self.assertIn("apkindex_apks", VERIFY_MODULE)
        self.assertIn("package_sets_equal", VERIFY_MODULE)
        self.assertIn("apk verify", VERIFY_MODULE)

    def test_verification_retries_index_updates_but_not_resolver_failures(self):
        verify_start = WORKFLOW.index("  verify:")
        publish_start = WORKFLOW.index("\n  publish:", verify_start)
        verify = WORKFLOW[verify_start:publish_start]
        self.assertIn("verify-repository.sh", verify)
        self.assertIn("--install-declared-builds", verify)
        self.assertIn("apk_update_with_retry", VERIFY_MODULE)
        self.assertIn("apk_add_pinned_origin", VERIFY_MODULE)
        self.assertNotIn("for delay in", verify)
        self.assertIn("package-origin=", (ROOT / "scripts" / "lib.sh").read_text())

    def test_staged_snapshot_is_installed_before_publication(self):
        verify_job = WORKFLOW.index("\n  verify:")
        publish_job = WORKFLOW.index("\n  publish:")
        self.assertLess(verify_job, publish_job)
        self.assertIn("verify:\n    needs: sign", WORKFLOW)
        self.assertIn("publish:\n    needs: verify", WORKFLOW)
        self.assertIn("snapshot_created: ${{ steps.snapshot.outputs.created }}", WORKFLOW)
        staged_verification = WORKFLOW[verify_job:publish_job]
        self.assertIn("if: needs.sign.outputs.snapshot_created == 'true'", staged_verification)
        self.assertNotIn("continue-on-error", staged_verification)
        self.assertIn("verify-repository.sh", staged_verification)
        self.assertIn("--install-declared-builds", staged_verification)
        self.assertNotIn("PAGES_URL", staged_verification)


if __name__ == "__main__":
    unittest.main()
