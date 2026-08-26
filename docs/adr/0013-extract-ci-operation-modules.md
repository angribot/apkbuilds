# Extract CI operations behind shell-module seams

Workflow YAML remains responsible for job orchestration, mounts, and explicit
parameters, while `scripts/build-package-family.sh`,
`scripts/sign-repository.sh`, and `scripts/verify-repository.sh` provide
independently testable build, signing, and verification operations. Only the
build module executes untrusted upstream build code and sees the public half of
the repository signing key and an ephemeral build key; merge validation remains
network-free before signing, and the persistent repository signing key is
mounted only into the network-isolated signing module. Signature-only verification is network-free,
while optional installation verification retains the network access required
for Alpine dependencies, exact-build checks, and bounded APK index retries.
