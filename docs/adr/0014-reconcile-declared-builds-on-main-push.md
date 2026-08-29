# Reconcile declared builds on every main push

Pull requests validate only changed package origins, while every push to `main`
reconciles each declared build for its origin-supported architectures with the
APK repository snapshot. Git history may optimize work but never defines
publication correctness, so a later CI fix rediscovers builds left unpublished
by an earlier failure without a
failed-build queue, scheduled recovery, or user-selected build scope. This
decision supersedes ADR-0009.
