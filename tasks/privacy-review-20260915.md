# Privacy and secrets review — 2026-09-15

## Result

**Current status after merging and pulling:** the published branch retained its
original ancestry. Pulling that branch restored historical personal paths,
author/committer identities, and references to other datasets to this checkout.
The local rewrite described below is an earlier checkpoint, not a statement
that the current history is anonymous. See the
[open-source review](open-source-review-20260915.md) for the current findings.

No secret credentials were detected in the reviewed source, fixtures,
documentation, dependency manifests, lockfile, or Git file history. The
checked-in fixtures are synthetic, and the review found no private application
records. Published history still contains personal identifiers, including
home paths and author/committer names and email addresses; those findings
remain unresolved despite the absence of credential or private-record findings.

At the earlier rewrite checkpoint, personal home-directory paths were removed
from current documentation and local Git history. All 19 local commits then
used anonymous author/committer identities; identifying text in their messages
was also sanitized.

## Changes

- Replaced personal absolute paths in README and the two audit reports with
  `$HOME` shell examples or `~` descriptive paths.
- Added repository ignore rules for environment files, private-key/container
  files, local assistant settings, and session state. `.env.example` remains
  eligible for tracking; its contents must use placeholders.
- Added a documentation/fixture privacy rule to the project instructions.

## Scope and method

- Reviewed tracked files and non-ignored untracked files, including current edits.
- Checked repository-local ignored settings/session files, excluding installed
  dependencies and generated caches. Local settings contain personal paths but
  are ignored and were not modified.
- Scanned 89 unique historical file blobs across all local refs and reflogs,
  covering 19 reachable commits; also checked commit metadata and local Git
  configuration without printing sensitive values.
- Used local pattern checks for private keys, provider tokens, credential
  assignments, authenticated URLs/query parameters, JWTs, email addresses,
  phone/SSN-shaped values, personal home paths, and high-entropy strings.
- Inspected the synthetic fixture values and dependency references. Public
  upstream repository URLs remain because they identify the pinned dependency;
  they include the public repository owner's account handle.

No dedicated Gitleaks/TruffleHog scanner was installed. CodeRabbit was not used
because its installed binary previously failed signature verification. Local
pattern checks and inspection can miss unusual or obfuscated sensitive data.
Remote-only refs, hosting-service artifacts, and external project folders were
outside this repository review.

## Approved local history rewrite

After explicit approval, replaced all 13 direct local branch and remote-tracking
refs with verified anonymized history, preserving the symbolic refs and ancestry.
Five historical file blobs needed home-path redaction; 17 commit messages changed.
Authors and committers now use
`Anonymous Contributor <contributor@example.invalid>`.

Expired local reflogs and pruned unreachable objects. Verified that all 19 old
commit objects are absent and that all 89 remaining file blobs pass the final
path, contact, and credential-pattern checks. Git object integrity passed.
All 31 working files were byte-for-byte preserved during the rewrite; this
report was updated afterward. No staged changes were introduced.

A private recovery bundle containing the original history is retained outside
the repository. It still contains the original identifying information.
No remote push was performed: remote history and other clones remain unchanged
and would require coordinated replacement. Git identity settings were left
unchanged, so future commits will use the existing configured identity.

## Validation

- Final current-file path/contact checks passed; public dependency URLs are retained.
- Ignore rules were verified for environment, key, local settings, and session files.
- 83 tests passed; `git diff --check` passed.
- Verified the rewritten refs, commit ancestry, anonymized metadata, absence of
  old commit objects, preserved working files, and Git object integrity.
