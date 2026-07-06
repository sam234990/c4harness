"""C4Harness command-line entry point."""

from .main import (
    async_task_command,
    build_parser,
    dashboard_command,
    decompose_command,
    external_policy_error,
    external_transfer_error,
    load_env_file_if_exists,
    main,
    make_claude_decision,
    memory_command,
    prepare_claude_backend,
    prepare_codex_backend,
    print_human,
    run_command,
    setup_command,
)

__all__ = [
    "async_task_command",
    "build_parser",
    "dashboard_command",
    "decompose_command",
    "external_policy_error",
    "external_transfer_error",
    "load_env_file_if_exists",
    "main",
    "make_claude_decision",
    "memory_command",
    "prepare_claude_backend",
    "prepare_codex_backend",
    "print_human",
    "run_command",
    "setup_command",
]
