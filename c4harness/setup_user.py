from __future__ import annotations

import importlib.resources
from pathlib import Path
import shutil
from typing import Any

from .memory import MemoryStore
from .config.paths import default_memory_path


def setup_user(*, force: bool = False) -> dict[str, Any]:
    memory_path = default_memory_path().resolve()
    MemoryStore(memory_path).init()

    skill_root = Path.home() / ".agents" / "skills"
    skill_target = skill_root / "c4harness"
    skill_root.mkdir(parents=True, exist_ok=True)
    skill_status = "kept"
    if not skill_target.exists() and not skill_target.is_symlink():
        _copy_bundled_skill(skill_target)
        skill_status = "installed"
    elif force:
        if skill_target.is_symlink() or skill_target.is_file():
            skill_target.unlink()
        else:
            shutil.rmtree(skill_target)
        _copy_bundled_skill(skill_target)
        skill_status = "updated"

    writable_root = memory_path.parent
    return {
        "memory_path": str(memory_path),
        "skill_path": str(skill_target),
        "skill_status": skill_status,
        "codex_config": (
            "[sandbox_workspace_write]\n"
            f'writable_roots = ["{writable_root}"]'
        ),
    }


def _copy_bundled_skill(target: Path) -> None:
    source = importlib.resources.files("c4harness.bundled_skill")
    with importlib.resources.as_file(source) as source_path:
        shutil.copytree(source_path, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
