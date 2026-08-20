"""Packaging contracts for the Orbien client/server package family."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
APKBUILD = (ROOT / "packages" / "orbien" / "APKBUILD").read_text()
INITD_PATH = ROOT / "packages" / "orbien" / "orbien-server.initd"
SMOKE_PATH = ROOT / "scripts" / "test-orbien.sh"


class OrbienPackageTest(unittest.TestCase):
    def test_declares_server_and_openrc_subpackages(self):
        self.assertIn(
            'subpackages="$pkgname-server:server '
            '$pkgname-server-openrc:server_openrc"',
            APKBUILD,
        )

        self.assertIn('depends="openrc $pkgname-server=$pkgver-r$pkgrel"', APKBUILD)
        self.assertIn('install_if="$pkgname-server=$pkgver-r$pkgrel openrc"', APKBUILD)

    def test_dashboard_uses_locked_npm_install_before_server_build(self):
        npm_install = APKBUILD.index("npm ci")
        dashboard_build = APKBUILD.index("npm run build", npm_install)
        server_build = APKBUILD.index("--package orbien-server", dashboard_build)
        self.assertLess(npm_install, dashboard_build)
        self.assertLess(dashboard_build, server_build)

    def test_rust_build_and_tests_are_limited_to_cli_packages(self):
        self.assertIn(
            "cargo build --release --frozen --package orbien-client", APKBUILD
        )
        self.assertIn(
            "cargo build --release --frozen --package orbien-server", APKBUILD
        )
        self.assertIn("--package orbien-server", APKBUILD[APKBUILD.index("check()") :])
        self.assertNotIn("--workspace", APKBUILD)
        self.assertNotIn("orbien-desktop", APKBUILD)

    def test_examples_are_documentation_not_live_configuration(self):
        self.assertIn("usr/share/doc/orbien/orbien.toml", APKBUILD)
        self.assertIn("usr/share/doc/orbien-server/orbien-server.toml", APKBUILD)
        self.assertNotIn("$pkgdir/etc/orbien/orbien-server.toml", APKBUILD)
        self.assertNotIn("$subpkgdir/etc/orbien/orbien-server.toml", APKBUILD)

    def test_openrc_service_has_fixed_root_configuration_contract(self):
        initd = INITD_PATH.read_text()
        self.assertIn('command="/usr/bin/orbien-server"', initd)
        self.assertIn('command_user="root:root"', initd)
        self.assertIn('command_args="-c /etc/orbien/orbien-server.toml"', initd)
        self.assertIn("command_background=true", initd)
        self.assertIn('pidfile="/run/$RC_SVCNAME.pid"', initd)
        self.assertIn("start_pre()", initd)
        self.assertIn(
            "orbien server config /etc/orbien/orbien-server.toml not found", initd
        )

    def test_smoke_test_covers_missing_config_and_successful_start(self):
        smoke = SMOKE_PATH.read_text()
        missing = smoke.index("/etc/init.d/orbien-server --nodeps start")
        config = smoke.index("/etc/orbien/orbien-server.toml", missing)
        successful_start = smoke.index(
            "/etc/init.d/orbien-server --nodeps start", config
        )
        alive = smoke.index('kill -0 "$pid"', successful_start)
        self.assertLess(missing, config)
        self.assertLess(config, successful_start)
        self.assertLess(successful_start, alive)


if __name__ == "__main__":
    unittest.main()
