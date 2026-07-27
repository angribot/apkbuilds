# Publish package families atomically

Treat one package origin on one architecture as publication's atomic unit. A
candidate must contain exactly the complete package family declared by
`abuild listpkg`; replacement removes every APK in that origin's previously
signed family before adding the candidate and rebuilding the signed index.

An origin-unsupported architecture produces no candidate and retains its
previous available build. A repeated build identity with a different package
set is rejected, preserving published build immutability. Any build, merge,
signing, or verification failure publishes no repository snapshot; partial
success across package origins is intentionally deferred.
