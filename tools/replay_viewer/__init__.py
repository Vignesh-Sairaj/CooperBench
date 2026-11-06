"""Three-pane log replay viewer for CooperBench multi-agent runs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tools.replay_viewer.compiler import (
    compile_pair_replay,
    list_pairs_index,
    list_runs,
)

if TYPE_CHECKING:
    from tools.replay_viewer.server import export_static_html as export_static_html

__all__ = [
    "compile_pair_replay",
    "export_static_html",
    "list_pairs_index",
    "list_runs",
]


def __getattr__(name: str) -> Any:
    if name == "export_static_html":
        from tools.replay_viewer.server import export_static_html

        return export_static_html
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
