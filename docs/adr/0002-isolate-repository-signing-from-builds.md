# Isolate repository signing from builds

Package builds execute untrusted upstream code, so they receive only an
ephemeral build key. The persistent repository signing key is confined to a
network-isolated signer, and signed output is then verified using only its
public key; this adds a signing stage but prevents build code from stealing
repository authority.
