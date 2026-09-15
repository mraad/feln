# Open-source readiness review — 2026-09-15

## Result

The GitHub repository is currently private. No credential patterns were found
in the scanned files or history, and OSV reported no known vulnerabilities for
the 15 locked PyPI package/version entries queried. These checks do not establish
that the repository is free of all secrets or vulnerabilities.

Current examples and test labels were cleaned so NorthSea is the only named
reference dataset; generic synthetic layer and feature labels remain. Historical
commits still contain references to other datasets and personal information.
The repository should not be described as fully sanitized for publication yet.

## Confirmed security findings

### High: compiler options can inject additional SQL statements

`feln/sql.py` interpolates geometry expressions, output aliases, and CRS strings
in the geometry-output paths without consistently validating or escaping them.
The CLI exposes the geometry option directly.

A harmless reproduction supplied a geometry value that closes `ST_AsText`,
adds `SELECT 42`, and opens another expression. The resulting SQL parsed as
three SELECT statements. A crafted output alias also produced three statements.
No statements were executed during this review.

Impact requires a downstream consumer to execute generated SQL with
attacker-controlled options. FELN itself only returns SQL text. Validate
geometry identifiers on every output path, quote/escape aliases and CRS values,
and add regression coverage before accepting these options from untrusted users.
The compiler behavior was not changed in this review.

### High for untrusted execution: the WHERE guard is not a sandbox

`feln/sanitize.py::sanitize_where_clause` accepts an EXISTS subquery invoking
`read_csv_auto` on an example temporary-file path. The blacklist does not
restrict the AST to allowed predicates, tables, columns, or functions.

A consumer executing that SQL can expose its process's filesystem/network
capabilities. Use explicit application-level query restrictions and OS-level
isolation; database settings alone are not a complete boundary. See
[DuckDB's security guidance](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview).
README now states the trust boundary and does not present the guard as a sandbox.

If exposed through a service, also bound input size, expression complexity,
runtime, and memory: normalization and predicate comparison process arbitrary
input, and the normalization cache bounds entry count rather than total bytes.
No service is implemented in this repository.

### Publication privacy: existing history was not sanitized remotely

The scan of all locally available refs/reflogs covered 108 unique file blobs.
Six historical blobs in `feln/generate.py` contain another dataset reference.
Five historical blobs in dependency files and the earlier audit contain personal
home paths. These findings are reachable from current main and the fetched
remote refs; they are not limited to an unused backup branch. Commit messages
and author/committer metadata also retain identifying information.

The earlier local anonymization was followed by a normal PR update that
preserved published ancestry. Merging and pulling therefore brought that
history back. Editing today's files does not remove it.

Before publication, choose and explicitly authorize either a clean public
history or a coordinated rewrite of all affected published branches/tags.
Also review PR discussions, attachments, releases, and other hosted artifacts;
this file/history scan does not certify those surfaces. No remote rewrite or
visibility change was made in this review.

## Other release concerns

- No LICENSE file or project license metadata is present; GitHub reports no
  detected license. The author must choose a license and confirm the rights to
  redistribute the code and any published data. Public visibility alone does
  not grant normal open-source reuse permissions. See
  [GitHub's licensing documentation](https://docs.github.com/en/enterprise-cloud%40latest/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).
- The pinned upstream Git commit was accessible at review time. OSV checks
  covered registry package versions in `uv.lock`, not the custom upstream source,
  build dependencies outside the lock, or every version permitted by broad
  dependency constraints in `pyproject.toml`.
- GitHub's repository response did not expose security-feature configuration,
  so secret scanning/push protection status was not established. Configure and
  verify those controls before publishing; ignore rules do not scan history.
- Publish only synthetic examples or data whose redistribution rights have
  been established. The checked-in catalog is synthetic; live project exports
  were not copied into this repository.

## Changes and validation

- Replaced unrelated place names with `County A` / `County B` fixture labels.
- Replaced domain-specific comparison examples with wells, depth, pressure,
  and pipeline-distance examples while retaining expected scores.
- Replaced the remaining dataset-derived catalog-name example with a generic
  `Features` layer and synthetic well subtype labels.
- Added the README security boundary and corrected the earlier privacy report's
  current-history claim.
- All 83 tests passed; lint, formatting, and diff checks passed.
- All seven README examples validated and compiled against the updated fixture.

Review used local inspection and harmless SQL-generation probes. No source code
was uploaded to an external review service. CodeRabbit was not run because its
installed binary previously failed signature verification. OSV received only
public package names and versions; see the [OSV API](https://google.github.io/osv.dev/post-v1-querybatch/).
