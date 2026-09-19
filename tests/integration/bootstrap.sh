#!/bin/sh
# Create an independent, signed baseline with ordinary abuild commands.
# Only this trusted fixture setup receives the temporary repository key.
set -eu

mkdir -p /seed/packages /seed/output
cp -R /fixtures/baseline/probe /seed/packages/apkbuilds-ci-probe
cp -R /fixtures/baseline/unrelated /seed/packages/apkbuilds-ci-unrelated
sh /workspace/scripts/prepare-builder.sh /seed/packages /seed/output
mkdir -p /home/builder/.config/abuild
cp /private-key /home/builder/.config/abuild/apkbuilds.rsa
cp /workspace/keys/apkbuilds.rsa.pub /home/builder/.config/abuild/apkbuilds.rsa.pub
cp /workspace/keys/apkbuilds.rsa.pub /etc/apk/keys/
printf '%s\n' 'PACKAGER_PRIVKEY="/home/builder/.config/abuild/apkbuilds.rsa"' \
  > /home/builder/.config/abuild/abuild.conf
chown -R builder:builder /home/builder/.config

for origin in apkbuilds-ci-probe apkbuilds-ci-unrelated; do
  su builder -c "cd /seed/packages/$origin && REPODEST=/seed/output abuild -r"
done

# noarch APKs are valid in both indexes; native compiled candidates replace
# only the runner's architecture later in the lifecycle test.
for arch in x86_64 aarch64; do
  directory=/seed/pages/edge/$arch
  mkdir -p "$directory"
  find /seed/output -type f -name '*.apk' -exec cp {} "$directory/" \;
  (
    cd "$directory"
    apk index --no-warnings --quiet --rewrite-arch "$arch" \
      --output APKINDEX.tar.gz ./*.apk
    abuild-sign -q -t RSA256 \
      -k /home/builder/.config/abuild/apkbuilds.rsa \
      -p /workspace/keys/apkbuilds.rsa.pub APKINDEX.tar.gz
    apk verify APKINDEX.tar.gz ./*.apk
  )
done
cp /workspace/keys/apkbuilds.rsa.pub /seed/pages/
touch /seed/pages/.nojekyll
