#!/usr/bin/env python3
"""Create and clean isolated git worktrees for per-paper worker agents."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
    )


def _fail(message: str, code: int = 1) -> int:
    print(f"[FAIL] {message}")
    return code


def _repo_root(cwd: Path) -> Path | None:
    proc = _run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        return None
    return Path(proc.stdout.strip()).resolve()


def _sanitize_slug(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", raw.strip())
    cleaned = cleaned.strip("-_.")
    return cleaned or "paper"


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Source path does not exist: {src}")
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def _resolve_repo_relative(repo_root: Path, raw_path: str) -> tuple[Path, str]:
    raw = Path(raw_path)
    abs_path = (repo_root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    try:
        rel = abs_path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Path must be under repository root: {abs_path}") from exc
    return abs_path, rel


def _resolve_under_root(root: Path, raw_path: str, label: str) -> Path:
    raw = Path(raw_path)
    if raw.is_absolute():
        raise ValueError(f"{label} must be a relative path under {root}: {raw_path}")
    abs_path = (root / raw).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes {root}: {raw_path}") from exc
    return abs_path


def _build_sandbox_paths(
    wt_path: Path,
    paper_rel: str,
    skill_rel: str,
    output_dir: str,
) -> tuple[list[str], list[str], str]:
    paper_path = (wt_path / paper_rel).resolve()
    output_path = (wt_path / output_dir).resolve()
    skill_root = (wt_path / skill_rel).resolve()

    allowed_rw = [
        str(paper_path),
        str(output_path),
    ]
    allowed_ro = [
        str(skill_root / "SKILL.md"),
        str(skill_root / "references"),
        str(skill_root / "scripts"),
    ]
    entry_cwd = str(paper_path)
    return allowed_rw, allowed_ro, entry_cwd


def _create(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    repo_root = _repo_root(cwd)
    if not repo_root:
        return _fail(
            "Current directory is not a git repository. Initialize git first and retry.",
            code=2,
        )

    try:
        paper_abs, paper_rel = _resolve_repo_relative(repo_root, args.paper_dir)
        skill_abs, skill_rel = _resolve_repo_relative(repo_root, args.skill_dir)
    except ValueError as exc:
        return _fail(str(exc))

    if not paper_abs.is_dir():
        return _fail(f"Paper folder not found: {paper_abs}")
    if not skill_abs.is_dir():
        return _fail(f"Skill folder not found: {skill_abs}")

    wt_root = (repo_root / args.worktrees_root).resolve()
    wt_root.mkdir(parents=True, exist_ok=True)

    slug = _sanitize_slug(Path(paper_rel).name)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = f"{stamp}-{Path.cwd().name}-{os.getpid()}"
    branch = f"{args.branch_prefix}/{slug}-{suffix}"
    wt_path = wt_root / f"{slug}-{suffix}"

    add_proc = _run(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "add",
            "-b",
            branch,
            str(wt_path),
            args.base_ref,
        ]
    )
    if add_proc.returncode != 0:
        return _fail(add_proc.stderr.strip() or add_proc.stdout.strip())

    try:
        _copy_tree(paper_abs, wt_path / paper_rel)
        _copy_tree(skill_abs, wt_path / skill_rel)
        output_dir_abs = _resolve_under_root(wt_path, args.output_dir, "Output dir")
        output_dir_abs.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        _run(["git", "-C", str(repo_root), "worktree", "remove", "--force", str(wt_path)])
        _run(["git", "-C", str(repo_root), "branch", "-D", branch])
        return _fail(f"Failed to prepare worktree payload: {exc}")

    sandbox_allowed_rw, sandbox_allowed_ro, sandbox_entry_cwd = _build_sandbox_paths(
        wt_path=wt_path,
        paper_rel=paper_rel,
        skill_rel=skill_rel,
        output_dir=args.output_dir,
    )

    result = {
        "repo_root": str(repo_root),
        "paper_rel": paper_rel,
        "skill_rel": skill_rel,
        "worktree_path": str(wt_path),
        "branch": branch,
        "output_dir": args.output_dir,
        "sandbox_allowed_rw": sandbox_allowed_rw,
        "sandbox_allowed_ro": sandbox_allowed_ro,
        "sandbox_entry_cwd": sandbox_entry_cwd,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _branch_for_worktree(repo_root: Path, worktree_path: Path) -> str | None:
    proc = _run(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "list",
            "--porcelain",
        ]
    )
    if proc.returncode != 0:
        return None

    branch: str | None = None
    current_path: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line.removeprefix("worktree ").strip()
            branch = None
            continue
        if line.startswith("branch "):
            branch = line.removeprefix("branch ").strip()
            if current_path and Path(current_path).resolve() == worktree_path.resolve():
                return branch.removeprefix("refs/heads/")
    return None


def _remove(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    repo_root = _repo_root(cwd)
    if not repo_root:
        return _fail(
            "Current directory is not a git repository. Initialize git first and retry.",
            code=2,
        )

    raw_wt = Path(args.worktree_path)
    wt_path = (repo_root / raw_wt).resolve() if not raw_wt.is_absolute() else raw_wt.resolve()
    if not wt_path.exists():
        return _fail(f"Worktree path does not exist: {wt_path}")

    branch = args.branch or _branch_for_worktree(repo_root, wt_path)
    rm_proc = _run(
        [
            "git",
            "-C",
            str(repo_root),
            "worktree",
            "remove",
            "--force",
            str(wt_path),
        ]
    )
    if rm_proc.returncode != 0:
        return _fail(rm_proc.stderr.strip() or rm_proc.stdout.strip())

    deleted_branch = False
    if args.delete_branch and branch:
        del_proc = _run(["git", "-C", str(repo_root), "branch", "-D", branch])
        if del_proc.returncode == 0:
            deleted_branch = True

    result = {
        "repo_root": str(repo_root),
        "worktree_path": str(wt_path),
        "branch": branch,
        "deleted_branch": deleted_branch,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage isolated git worktrees for CFST workers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create", help="Create one isolated worktree for one paper.")
    create.add_argument("--paper-dir", required=True, help="Paper folder path under repository root.")
    create.add_argument(
        "--skill-dir",
        default=".codex/skills/cfst-paper-extractor",
        help="Skill folder path under repository root.",
    )
    create.add_argument(
        "--worktrees-root",
        default=".codex/worktrees",
        help="Where to create per-paper worktrees.",
    )
    create.add_argument(
        "--branch-prefix",
        default="cfst-worker",
        help="Branch prefix for worker worktrees.",
    )
    create.add_argument("--base-ref", default="HEAD", help="Base git ref for worktree creation.")
    create.add_argument("--output-dir", default="output", help="Output directory under worktree root.")

    remove = sub.add_parser("remove", help="Remove one isolated worktree.")
    remove.add_argument("--worktree-path", required=True, help="Worktree path (absolute or repo-relative).")
    remove.add_argument("--branch", default=None, help="Optional branch name to delete.")
    remove.add_argument(
        "--delete-branch",
        action="store_true",
        help="Delete branch after worktree removal.",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if args.cmd == "create":
        return _create(args)
    if args.cmd == "remove":
        return _remove(args)
    return _fail(f"Unsupported command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
