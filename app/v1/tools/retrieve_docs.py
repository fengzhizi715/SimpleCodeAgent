"""文档检索工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.core.exceptions import RagIdValidationError
from app.v1.rag.rag_id_policy import strict_normalize_v2_rag_ids
from app.v1.rag.retriever import DocumentRetriever
from app.v1.tools.base import Tool


class RetrieveDocsTool(Tool):
    """从文档知识库中检索相关片段。"""

    def __init__(
        self,
        workspace_root: str | None = None,
        retriever: DocumentRetriever | None = None,
        *,
        allow_multi_rag: bool = False,
    ) -> None:
        super().__init__(workspace_root=workspace_root)
        self.retriever = retriever if retriever is not None else DocumentRetriever()
        self._allow_multi_rag = allow_multi_rag

    @property
    def definition(self) -> ToolDefinition:
        properties: dict[str, object] = {
            "query": {"type": "string", "description": "检索问题或关键词。"},
            "top_k": {
                "type": "integer",
                "description": "返回的片段数量。",
                "default": 3,
            },
            "rerank": {
                "type": "boolean",
                "description": "是否对向量检索结果进行轻量重排。",
                "default": True,
            },
            "fetch_k": {
                "type": "integer",
                "description": "重排前召回的候选数量，默认自动使用更大的候选集。",
            },
            "min_score": {
                "type": "number",
                "description": "最小相似度分数阈值，范围建议 0.0 到 1.0。",
                "default": 0.0,
            },
        }
        if self._allow_multi_rag:
            properties["rag_id"] = {
                "type": "string",
                "description": "可选知识库标识；不传时使用默认知识库。",
            }
            properties["rag_ids"] = {
                "type": "array",
                "description": "可选知识库标识列表；传入时执行多库并查并统一重排。",
                "items": {"type": "string"},
            }
        return ToolDefinition(
            name="retrieve_docs",
            description="从 docs 知识库中检索与当前问题最相关的文档片段。",
            parameters={
                "type": "object",
                "properties": properties,
                "required": ["query"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        top_k = int(arguments.get("top_k", 3))
        rerank = bool(arguments.get("rerank", True))
        if self._allow_multi_rag:
            rag_id = str(arguments.get("rag_id", "")).strip() or None
            raw_rag_ids = arguments.get("rag_ids")
            rag_ids = (
                [str(item).strip() for item in raw_rag_ids if str(item).strip()]
                if isinstance(raw_rag_ids, list)
                else None
            )
        else:
            rag_id = None
            rag_ids = None
        raw_fetch_k = arguments.get("fetch_k")
        fetch_k = int(raw_fetch_k) if raw_fetch_k is not None else None
        min_score = float(arguments.get("min_score", 0.0))
        if not query:
            return self.error(tool_call_id=tool_call_id, message="Query must not be empty.")

        if self._allow_multi_rag:
            try:
                resolved_list = strict_normalize_v2_rag_ids(rag_id=rag_id, rag_ids=rag_ids)
            except RagIdValidationError as exc:
                return self.error(tool_call_id=tool_call_id, message=str(exc))
            if len(resolved_list) == 1:
                use_rag_id, use_rag_ids = resolved_list[0], None
            else:
                use_rag_id, use_rag_ids = None, resolved_list
        else:
            resolved_list = ["default"]
            use_rag_id, use_rag_ids = None, None

        results = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            min_score=min_score,
            rerank=rerank,
            fetch_k=fetch_k,
            rag_id=use_rag_id,
            rag_ids=use_rag_ids,
        )
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "query": query,
                "rag_id": resolved_list[0],
                "rag_ids": resolved_list,
                "top_k": top_k,
                "rerank": rerank,
                "fetch_k": fetch_k,
                "min_score": min_score,
                "match_count": len(results),
                "matches": results,
            },
        )
