"""文档检索工具。"""

from __future__ import annotations

from app.contracts.tool import ToolDefinition, ToolResult
from app.v1.rag.retriever import DocumentRetriever
from app.v1.tools.base import Tool


class RetrieveDocsTool(Tool):
    """从文档知识库中检索相关片段。"""

    def __init__(self) -> None:
        self.retriever = DocumentRetriever()

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="retrieve_docs",
            description="从 docs 知识库中检索与当前问题最相关的文档片段。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索问题或关键词。"},
                    "top_k": {
                        "type": "integer",
                        "description": "返回的片段数量。",
                        "default": 3,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: dict[str, object], tool_call_id: str) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        top_k = int(arguments.get("top_k", 3))
        if not query:
            return self.error(tool_call_id=tool_call_id, message="Query must not be empty.")

        results = self.retriever.retrieve(query=query, top_k=top_k)
        return self.success(
            tool_call_id=tool_call_id,
            content={
                "ok": True,
                "query": query,
                "top_k": top_k,
                "matches": results,
            },
        )
