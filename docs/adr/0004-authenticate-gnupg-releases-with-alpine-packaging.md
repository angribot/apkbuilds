# Authenticate GnuPG releases while retaining Alpine packaging

Track eligible GnuPG upstream releases while retaining Alpine edge's package
split, build options, patches, and dependencies rather than maintaining an
independent packaging design. Authenticate each upstream release using both a
checked-in upstream release key and its code-pinned fingerprint: replacing the
key file alone must not authorize a new signer. Abandoning the Alpine baseline
would create an independently maintained package design, while dropping the
fingerprint pin would silently widen signer authority, so both constraints
remain part of the release trust boundary.
