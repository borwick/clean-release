# PUBLIC-REPO

The public repo is the private repo's twin, by convention a sibling
directory `<repo>-public`: one commit and one annotated tag per release,
nothing else. Written only by `commit` (`src/clean_release/commit.py`);
`diff` and `status` read it and never write.

- **Where:** the machine config's `[repos.<name>] public`, else the
  policy's `[release] public`, `~` expanded (`public_path`); `doctor`
  reads it the same way. Neither set refuses.
- **One commit per release.** Its tree is the approved staging tree,
  rewritten into the public repo's objects from the staging HEAD's
  entries and blobs (`git.write_tree`); a tree SHA that differs from the
  approval refuses. Its parent is the last release's commit, none on the
  first; author and committer are the machine config's `[identity]`; its
  message is `[release] message` with `{version}` filled in. No stage
  commit enters the public repo.
- **The tag** is `[release] tag` for the version, annotated, the same
  message, its tagger `[identity]`. The last release is the highest tag
  matching `[release] tag`, versions compared as dotted integers.
- **The directory is never removed, re-created or made.** HEAD moves by
  `update-ref` compare-and-swap, then `read-tree -m -u` brings the index
  and work tree along, removing what the release dropped. A missing
  directory refuses and prints its `mkdir -p`; an empty one gets `git
  init -b main` once every refusal has passed.
- **Refused before anything is written:** a version that is not dotted
  integers; a missing directory; a non-empty directory that is not a git
  repo; one inside another repo; a detached HEAD; any line from `git
  status --porcelain --untracked-files=all`; a tag that already exists;
  commits but no matching tag; a HEAD that is not the last tag's commit;
  a version not newer than the last tag.
- **After the commit and tag,** `git status` is read again; any line is
  reported and `commit` exits 1, the commit and tag kept. The push
  commands print either way, with `remote add origin <URL>` first when
  there is no `origin`.
- **`diff`** (`diff.py`) diffs the staging HEAD's tree against the public
  `HEAD^{tree}`, the staging repo reading the public objects through
  `GIT_ALTERNATE_OBJECT_DIRECTORIES`, so neither repo gains an object.
  With no public commit it diffs against the empty tree. It runs `check`
  and exits as `check` does; none of `commit`'s refusals apply.
- **`status`** (`status.py`) reports the last public version (the highest
  matching tag), the staged version, whether the approval is for the
  staged tree, and the public tree: clean, missing, empty, not a git
  repo, or its uncommitted lines. It refuses only when the policy or the
  machine config does not load, and exits 0.
