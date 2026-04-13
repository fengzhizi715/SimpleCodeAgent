"""写入意图解析器。"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class WriteIntentParseResult:
    """记录写入意图解析结果，避免解析失败时静默返回 None。"""

    arguments: dict[str, object] | None = None
    error: str | None = None
    format_hint: str | None = None

    @property
    def ok(self) -> bool:
        """是否成功提取到 write_file 所需的结构化参数。"""
        return self.arguments is not None


class WriteIntentParser:
    """从模型输出中提取 write_file 所需的结构化参数。"""

    def parse_json_object(self, text: str) -> dict[str, object] | None:
        """尽量将完整文本解析为 JSON 对象。"""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    def extract_json_object(self, text: str) -> dict[str, object] | None:
        """从普通文本或 fenced code block 中尽量提取 JSON 对象。"""
        payload = self.parse_json_object(text)
        if payload is not None:
            return payload

        stripped = text.strip()
        fence_markers = ["```json", "```"]
        for marker in fence_markers:
            start = stripped.find(marker)
            if start == -1:
                continue
            content_start = start + len(marker)
            end = stripped.find("```", content_start)
            if end == -1:
                continue
            candidate = stripped[content_start:end].strip()
            payload = self.parse_json_object(candidate)
            if payload is not None:
                return payload

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = stripped[start : end + 1]
            return self.parse_json_object(candidate)
        return None

    def build_write_file_arguments_from_text(self, text: str) -> dict[str, object] | None:
        """从文本中提取 write_file 所需的 path 和 content。"""
        return self.parse_write_file_arguments(text).arguments

    def parse_write_file_arguments(self, text: str) -> WriteIntentParseResult:
        """从文本中提取 write_file 参数，并在失败时返回结构化原因。"""
        payload = self.extract_json_object(text)
        if not payload:
            path = self.extract_path_from_text(text)
            content = self.extract_code_block_content(text)
            if path is not None and content is not None:
                return WriteIntentParseResult(
                    arguments={
                        "path": path,
                        "content": content,
                        "dry_run": False,
                    },
                    format_hint="path_and_code_block",
                )
            if path is not None and content is None:
                return WriteIntentParseResult(
                    error="检测到 path，但未找到 fenced code block 形式的文件内容。",
                    format_hint="path_without_code_block",
                )
            if path is None and content is not None:
                return WriteIntentParseResult(
                    error="检测到代码块，但未找到 path 字段。",
                    format_hint="code_block_without_path",
                )
            return WriteIntentParseResult(
                error="未检测到可用于 write_file 的 JSON、path 字段或代码块。",
                format_hint="no_supported_pattern",
            )
        nested_arguments = payload.get("arguments")
        if isinstance(nested_arguments, dict):
            nested_path = nested_arguments.get("path")
            nested_content = nested_arguments.get("content")
            if isinstance(nested_path, str) and nested_path.strip() and isinstance(nested_content, str):
                return WriteIntentParseResult(
                    arguments={
                        "path": nested_path.strip(),
                        "content": nested_content,
                        "dry_run": False,
                    },
                    format_hint="nested_write_file_arguments",
                )
            return WriteIntentParseResult(
                error="检测到 arguments 对象，但缺少合法的 path/content 字段。",
                format_hint="invalid_nested_arguments",
            )
        path = payload.get("path")
        content = payload.get("content")
        if isinstance(path, str) and path.strip() and isinstance(content, str):
            return WriteIntentParseResult(
                arguments={
                    "path": path.strip(),
                    "content": content,
                    "dry_run": False,
                },
                format_hint="top_level_json",
            )
        return WriteIntentParseResult(
            error="检测到 JSON 对象，但缺少合法的 path/content 字段。",
            format_hint="invalid_json_payload",
        )

    def extract_path_from_text(self, text: str) -> str | None:
        """从普通文本中提取 path: xxx 形式的相对路径。"""
        stripped = text.strip()
        for line in stripped.splitlines():
            candidate = line.strip()
            lower = candidate.lower()
            if lower.startswith("path:"):
                path = candidate.split(":", 1)[1].strip().strip("`").strip('"')
                if path:
                    return path
            if '"path"' in candidate and ":" in candidate:
                _, value = candidate.split(":", 1)
                path = value.strip().rstrip(",").strip("`").strip('"')
                if path:
                    return path
        return None

    def extract_code_block_content(self, text: str) -> str | None:
        """提取文本中的第一个 fenced code block 作为文件内容。"""
        stripped = text.strip()
        start = stripped.find("```")
        if start == -1:
            return None
        newline_after_fence = stripped.find("\n", start)
        if newline_after_fence == -1:
            return None
        end = stripped.find("```", newline_after_fence + 1)
        if end == -1:
            content = stripped[newline_after_fence + 1 :]
        else:
            content = stripped[newline_after_fence + 1 : end]
        content = content.strip("\n")
        return content or None
