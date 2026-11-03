# Contributing

## Setup

Follow the [Development](README.md#development) section of the README: it lists the install, lint, type check, unit
test, JavaScript lint and browser test commands. Run them from the project root before opening a pull request.

## Branches and commits

- Branch from an up-to-date `main`, named `<type>/<slug>` (for example `feat/worker-interrupt`,
  `docs/release-process`).
- Commit header `type(scope): summary`, 72 characters at most, in English, imperative mood. Types in use: `feat`,
  `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `style`, `security`, `revert`. The body says
  why, and ends with `Spec: <SP-ID>`.
- Everything written into the repository is in American English, without emojis, end-of-line comments, `noqa`
  markers, attribution or `Co-authored-by` lines.
- The pull request title is the commit header; the body summarizes the change and carries `Spec: <SP-ID>`. Pull
  requests are squash-merged into `main`.

## Spec first

Every change starts from a spec in `docs/specs/`, written from `docs/specs/_TEMPLATE.md` and named
`<date>_<SP-ID>_<slug>.md`. The spec declares what the change owns and depends on, and reaches `status: approved`
with an empty Open Questions section before the implementation starts. Once the pull request is open, run the
review loop from the project root:

```bash
repoach review pr <N> --dry-run     # review, post nothing
repoach review gate <N>             # evidence-first merge gate
```

Fix every real finding in a new commit, push, and run both again until the gate passes.

## Changelog

Every pull request adds one line per user-visible change to `CHANGELOG.md` under `[Unreleased]`, in the matching
subsection (Added, Changed, Deprecated, Removed, Fixed, Security), ending with the pull request number in
parentheses. The release workflow publishes that section as the release notes, so write for the user, not for the
reviewer. The release procedure is in the [Contributing](README.md#contributing) section of the README.

## License

Sparring is licensed under the GNU Affero General Public License v3.0 or later ([LICENSE](LICENSE)). By contributing,
you agree that your contribution is licensed under the same license.
