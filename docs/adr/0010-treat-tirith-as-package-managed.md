# Treat Tirith as managed by Alpine's package manager

Treat Tirith installations from the APK repository as managed by Alpine's
package manager, even though the binary is compiled locally rather than copied
from an upstream release. Keep the downstream package-manager integration
needed for Tirith to identify the installation as source-built rather than
tampered, delegate upgrades to `apk upgrade tirith`, and never replace files
owned by the installed package. This creates an ongoing patch-maintenance cost,
but avoids conflicting ownership and misleading integrity warnings; issue #55
records the package implementation requirements.
