# Demo release checklist

This is a proposed checklist. `v1.0.0-demo` was not present when the source was checked, and this document does not assert that a release has been published.

## Source baseline and scope

The inspected source is `b8d62771abc9353933b6cb1e69ae237b27546381`. Day 27 code was first published at `f9b7630`; the historic container execution uses `f8267a8`. These snapshots are not a new Day 28 CI result.

A public demo release should identify the exact tested source, settings, data snapshots and assets. Its description must distinguish the local SQLite path, phone creation/lookup observations, and the volunteer workflow's actual completion state.

## Publication conditions

- Verify the complete source commit and the matching CI run and scope.
- Exercise the Quickstart from the packaged source, including an existing-output-directory failure.
- Review LICENSE, data/media rights, and CONTRIBUTING.md.
- Document actual cloud integration results. A two-phone release claim requires both verified accounts, the same authoritative request, notification/claim/readback evidence and the deployed image/revision.
- Build a manifest with relative paths, sizes and SHA-256; exclude the manifest itself.
- Include release notes, known limitations, deployment settings and rollback instructions without secrets.

The maintainer creates and publishes tags and releases. For an annotated tag, select the verified full commit, use the name `v1.0.0-demo`, and provide a precise annotation. This package does not execute any tag, commit, push or release operation.

## Verify after the maintainer publishes

```bash
git rev-parse 'v1.0.0-demo^{commit}'
git ls-remote origin 'refs/tags/v1.0.0-demo*'
```

For an annotated tag, distinguish the tag-object ID from the peeled commit ID. Compare the latter with the approved release source. These commands are instructions, not evidence that the tag already exists.

Ordinary tags can be moved by authorized users. Where immutable releases are enabled, prepare all assets on a draft release before publishing. Release immutability does not freeze Cloud Run traffic, hosted models, prompts stored elsewhere, credentials or third-party data.

Sources: [git-tag](https://git-scm.com/docs/git-tag), [GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
