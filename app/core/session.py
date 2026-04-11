"""会话标识相关工具。"""

from __future__ import annotations

import hashlib
from pathlib import Path


def derive_project_session_id(session_id: str, workdir: str | None) -> str:
    """当存在工作目录时，为 session_id 派生稳定的项目级会话标识。"""
    if not session_id or not workdir:
        return session_id

    normalized_workdir = str(Path(workdir).expanduser().resolve())
    workdir_hash = hashlib.sha1(normalized_workdir.encode("utf-8")).hexdigest()[:10]
    return f"{session_id}@{workdir_hash}"
