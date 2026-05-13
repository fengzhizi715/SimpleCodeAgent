"""Built-in retrieve-docs skill for V3."""

from __future__ import annotations

from app.v3.adapters.v1_tool_adapter import V1ToolAdapter
from app.v3.contracts.skill_contracts import SkillInput, SkillOutput
from app.v3.skills.base import Skill


class RetrieveDocsSkill(Skill):
    """Retrieve documentation context through the shared V1 retrieve_docs tool adapter."""

    def __init__(self, spec, docs_adapter: V1ToolAdapter) -> None:
        super().__init__(spec)
        self.docs_adapter = docs_adapter

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        query = str(
            skill_input.payload.get("query")
            or skill_input.payload.get("goal")
            or skill_input.context.get("user_goal")
            or ""
        ).strip()
        if not query:
            return SkillOutput(
                success=False,
                summary="retrieve_docs requires a non-empty query",
                error="Missing query for retrieve_docs skill.",
            )

        payload = {
            "query": query,
            "top_k": int(skill_input.payload.get("top_k", 3)),
            "rerank": bool(skill_input.payload.get("rerank", True)),
            "fetch_k": skill_input.payload.get("fetch_k"),
            "min_score": float(skill_input.payload.get("min_score", 0.0)),
        }
        rag_id = skill_input.payload.get("rag_id")
        rag_ids = skill_input.payload.get("rag_ids")
        if rag_id is not None:
            payload["rag_id"] = rag_id
        if rag_ids is not None:
            payload["rag_ids"] = rag_ids

        result = await self.docs_adapter.run(payload)
        if not bool(result.get("ok", False)):
            return SkillOutput(
                success=False,
                summary="retrieve_docs failed",
                error=str(result.get("error") or "Unknown retrieve_docs error."),
            )
        match_count = int(result.get("match_count", 0))
        return SkillOutput(
            success=True,
            summary=f"Retrieved {match_count} docs match(es)",
            data=result,
        )
