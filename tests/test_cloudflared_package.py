import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "packages" / "cloudflared"
APKBUILD = (PACKAGE / "APKBUILD").read_text()
INITD = (PACKAGE / "cloudflared.initd").read_text()
PRE_INSTALL = (PACKAGE / "cloudflared.pre-install").read_text()
CONFIG = (PACKAGE / "config.yml").read_text()
SMOKE = (ROOT / "scripts" / "test-cloudflared.sh").read_text()
BUILD_FAMILY = (ROOT / "scripts" / "operations" / "build-package-family.sh").read_text()


class CloudflaredPackageTest(unittest.TestCase):
    def test_declares_supported_package_family(self):
        self.assertIn('pkgname=cloudflared', APKBUILD)
        self.assertIn('arch="x86_64 aarch64"', APKBUILD)
        self.assertIn('subpackages="$pkgname-doc $pkgname-openrc"', APKBUILD)
        self.assertIn('pkgusers="$pkgname"', APKBUILD)
        self.assertIn('pkggroups="$pkgname"', APKBUILD)
        self.assertIn('install="$pkgname.pre-install"', APKBUILD)
        self.assertNotIn("loongarch64", APKBUILD)
        self.assertNotIn("loongarch64-support.patch", APKBUILD)

    def test_builds_from_vendored_go_dependencies_as_static_binary(self):
        self.assertIn('makedepends="go gettext"', APKBUILD)
        self.assertIn("go mod vendor", APKBUILD)
        self.assertIn(
            'export CGO_ENABLED=0 GOFLAGS="-mod=vendor -trimpath" VERSION DATE', APKBUILD
        )
        self.assertIn('make VERSION="$VERSION" DATE="$DATE" cloudflared', APKBUILD)
        self.assertIn('envsubst < cloudflared_man_template > cloudflared.1', APKBUILD)
        self.assertIn('options="!check net"', APKBUILD)

    def test_installs_binary_man_page_and_service_inputs(self):
        self.assertIn('install -D -m755 ./cloudflared "$pkgdir"/usr/bin/cloudflared', APKBUILD)
        self.assertIn(
            'install -D -m644 ./cloudflared.1 "$pkgdir"/usr/share/man/man1/cloudflared.1',
            APKBUILD,
        )
        self.assertIn(
            'install -D -m755 "$srcdir"/$pkgname.initd "$pkgdir"/etc/init.d/$pkgname',
            APKBUILD,
        )
        self.assertIn(
            'install -D -m644 "$srcdir"/config.yml "$pkgdir"/etc/$pkgname/config.yml',
            APKBUILD,
        )

    def test_openrc_service_uses_fixed_config_and_unprivileged_account(self):
        self.assertIn("command=/usr/bin/cloudflared", INITD)
        self.assertIn("command_user=cloudflared:cloudflared", INITD)
        self.assertIn('command_background="yes"', INITD)
        self.assertIn("pidfile=/run/${RC_SVCNAME}.pid", INITD)
        self.assertIn("need net", INITD)
        self.assertNotRegex(INITD, r"(?i)(setcap|capabilities|root:root)")
        self.assertIn(
            'command_args="tunnel --config /etc/cloudflared/config.yml run"',
            INITD,
        )

    def test_preinstall_creates_system_account(self):
        self.assertIn("addgroup -S cloudflared", PRE_INSTALL)
        self.assertIn(
            "adduser -S -D -s /sbin/nologin -G cloudflared -g cloudflared cloudflared",
            PRE_INSTALL,
        )

    def test_config_is_a_non_live_example_for_both_tunnel_modes(self):
        self.assertIn("credentials-file:", CONFIG)
        self.assertIn("token-file:", CONFIG)
        active_lines = [
            line.strip()
            for line in CONFIG.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(active_lines, [])

    def test_service_fails_clearly_without_operator_configuration(self):
        self.assertIn("start_pre()", INITD)
        self.assertIn("credentials-file or token-file", INITD)
        self.assertIn("cloudflared configuration", INITD)
        self.assertIn("expected the service to fail", SMOKE)
        self.assertIn("does not test a real tunnel connection", SMOKE)

    def test_smoke_checks_cli_docs_service_and_missing_configuration(self):
        self.assertIn('cloudflared --version | grep -F "$version"', SMOKE)
        self.assertIn("/usr/share/man/man1/cloudflared.1", SMOKE)
        self.assertIn("/etc/cloudflared/config.yml", SMOKE)
        self.assertIn("service=/etc/init.d/cloudflared", SMOKE)
        self.assertIn('"$service" --nodeps start', SMOKE)
        self.assertIn("command_user=cloudflared:cloudflared", SMOKE)
        self.assertRegex(SMOKE, r"grep -F.*credentials-file")
        self.assertRegex(SMOKE, r"grep -F.*token-file")
        self.assertIn("operator-supplied test daemon", SMOKE)

    def test_build_automation_runs_package_smoke_test(self):
        self.assertIn(
            "cloudflared)\n    \"$workspace/scripts/test-cloudflared.sh\"",
            BUILD_FAMILY,
        )


if __name__ == "__main__":
    unittest.main()
