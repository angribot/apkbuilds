# Service subpackages ship no live config

Service subpackages in this repository install an init script but no config
the service could start with: a fresh `rc-service <name> start` fails loudly
(an init-script `start_pre()` existence check) until the operator provides
one, because a default config would open ports or bind local services with
default credentials on every install. Paths are fixed in the init script (no
confd), the package creates the daemon's working directory because the
daemon refuses to start without it, and CI smoke-tests both the failure and
the success scenario per architecture.
