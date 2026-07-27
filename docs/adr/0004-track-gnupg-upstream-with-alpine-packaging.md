# Track GnuPG upstream with Alpine packaging

Track eligible GnuPG upstream releases while retaining Alpine edge's package
split, build options, patches, and dependencies. Authenticate source releases
using both checked-in upstream release keys and code-pinned fingerprints; this
keeps GnuPG current, limits packaging divergence, and prevents key-file
replacement alone from authorizing a new signer.
