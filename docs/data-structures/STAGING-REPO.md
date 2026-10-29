# STAGING-REPO

The staging repo holds the export `stage` built: a git repo of its own at
the private repo's `local/clean-release/`, kept between runs. Written by
`src/clean_release/stage.py`.

- **One commit per `stage`,** its message `stage <version> <tag commit>`,
  its parent the previous stage, made with the machine config's
  `[identity]`. Its `HEAD^{tree}` is the tree of record: `check` grades
  it, and `approve` and `commit` read its SHA and version.
- **The approval** is `<git-dir>/clean-release-approved`, one line
  `<tree SHA> <version>`, written by `approve` only when `check` passes
  (`src/clean_release/approve.py`). It lives in no tree, and `stage`
  leaves it alone: `commit` refuses when HEAD's tree or version is not
  the approved one, naming both trees.
- **Built at the object level.** Each blob is written with `git
  hash-object -w`, the tree with `update-index --index-info` into a
  scratch index and `write-tree` (`git.write_tree`, which `commit` also
  uses for the public repo), so modes (exec bit, symlink, gitlink)
  are kept and a shipped `.gitignore` cannot drop a file. `read-tree
  --reset -u HEAD` then makes the work tree match, removing what a later
  tag dropped.
- **`check` reads HEAD, never the work tree:** the tree from
  `HEAD^{tree}`'s objects, the version and tag commit from HEAD's
  message (`staged` in `stage.py`). It rebuilds the export under the
  current policy (`build`), and a staged tree that differs in a path,
  mode or content fails until the next `stage`. For the secrets scanner and
  `[verify]` it writes a temporary copy from those objects, modes kept,
  gitlinks left out.
- **Nothing is written until every check passes,** and `stage` refuses
  when the private repo does not ignore `local/clean-release`, so it
  cannot pick up the nested repo.
