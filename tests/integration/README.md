# Repository lifecycle integration test

This test exercises the public build, sign, verify, and publish scripts with
real Docker containers, abuild, apk, signatures, and a local Git remote. It uses
a small C program and a data subpackage instead of compiling production origins.

## Run locally

Requirements: Python 3.9 or newer, Git, OpenSSL, and a running Docker daemon on
that same Linux host, matching the requested native architecture. Docker must
allow bind mounts and its default bridge network. The harness serves the
baseline with Python's standard-library HTTP server, bound to the bridge gateway.
No separate HTTP image or package is needed. Alpine edge images and build tools
are downloaded, so the test needs network access.

On macOS, run the harness inside a Linux VM that also runs Docker. Running the
harness directly on macOS against a Docker Desktop or remote daemon is not
supported because the bridge address belongs to the daemon's Linux host.

```sh
python3 tests/integration/run.py --arch aarch64
# On an x86_64 host:
python3 tests/integration/run.py --arch x86_64
```

Logs default to `.cache/ci-integration/`; use `--logs DIRECTORY` to choose another
location. Each operation has its own log. Run only one lifecycle test at a time
per Docker daemon because the production signer uses a fixed image tag.

The harness creates a temporary workspace with copies of the current operation
scripts, its own repository key, and a locally served signed baseline. The
baseline contains an old package family with a retired split package and an
unrelated package. Its `noarch` APKs populate both architecture directories;
the new C program is compiled only for the runner's native architecture.

The repository private key is supplied only to trusted baseline setup and the
public signing operation. The actual build operation receives the public half
and generates its own build key. Production credentials and repository URLs
are not needed. Publication targets a temporary local bare Git repository and
does not contact SSH, GitHub, or Pages. Cleanup stops the HTTP server and removes
temporary keys and the workspace; Docker's downloaded/built images remain cached.

## Coverage

- Build the declared new family, then merge, sign, and install it through the
  public operation scripts. In a separate clean, offline container, install the
  signed main package and its declared data dependency and execute the program.
- Check complete replacement of the old family, including removal of its
  retired split package, and exact index/physical package-set agreement.
- Preserve unrelated APK bytes and the other architecture's APKs and indexed
  package set. The signer regenerates indexes, so compressed index bytes are
  not required to remain identical.
- Repeat against the published fixture using a fresh output directory: no
  candidates and no new signed snapshot may be emitted.
- Reject the same build identity with a different declared package family.
- Reject a modified signature while retaining the APK's payload and tar header.
- Publish the verified snapshot locally and compare its complete file tree and
  source revision with the expected snapshot.

A new build is selected by an older baseline identity, following the normal
production path. There is no force-build option or change to published identity
semantics. The test does not assess upstream compatibility, real Pages delivery,
or the periodic health of production packages.

## CI selection and gate

`plan-origins.sh` selects this check on PRs and main pushes that change:

- `.github/workflows/ci.yml`;
- public build, sign, verify, and publish scripts;
- `lib.sh`, `prepare-builder.sh`, `plan-origins.sh`, or `check-declared-build.sh`;
- anything under `scripts/operations/` or non-Markdown files under
  `tests/integration/`.

Production package-origin selection stays independent. Documentation-only,
updater-only, and package-only changes do not select this additional test.
Fixture and harness changes select it so the test validates its own inputs.

Both native `x86_64` and `aarch64` jobs must pass when selected. The existing
`ci` check treats a selected job's failure, cancellation, or unexpected skip as
failure. Unselected jobs may be skipped. Failure logs are retained as CI
artifacts for seven days; temporary keys and package workspaces are not uploaded.
