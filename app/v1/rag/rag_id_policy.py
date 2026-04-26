"""RAG 标识规范化与 V2 严格校验（与创建知识库接口语义一致）。"""

from __future__ import annotations

from app.core.exceptions import RagIdValidationError
from app.v1.rag.vector_store import normalize_rag_id_value


def strict_normalize_v2_rag_tokens(raw_tokens: list[str]) -> list[str]:
    """对非空原始 token 做规范化与去重；空列表表示使用 default。

    规则与 ``POST /debug/rag/collections`` 一致：若规范化结果为 default 且用户并非显式输入
    ``default``（大小写不敏感），则拒绝。
    """
    tokens = [str(t).strip() for t in raw_tokens if str(t).strip()]
    if not tokens:
        return ["default"]
    out: list[str] = []
    seen: set[str] = set()
    for raw in tokens:
        normalized = normalize_rag_id_value(raw)
        if normalized == "default" and raw.lower() != "default":
            raise RagIdValidationError(
                f'rag_id "{raw}" 在规范化后等同于 default，请直接使用 default。'
            )
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def strict_normalize_v2_rag_ids(*, rag_id: str | None, rag_ids: list[str] | None) -> list[str]:
    """合并 API 的 rag_id / rag_ids 字段后做严格规范化（顺序：rag_ids 各项，再 rag_id）。"""
    merged: list[str] = []
    if isinstance(rag_ids, list):
        merged.extend(str(item) for item in rag_ids)
    if rag_id is not None:
        merged.append(str(rag_id))
    return strict_normalize_v2_rag_tokens(merged)
