"""Parse a Claude Code session transcript (JSONL) into tool calls + human texts."""
from __future__ import annotations
import json
from dataclasses import dataclass, field

_CLIP = 400


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    is_error: bool = False
    result_text: str = ""
    seq: int = -1


@dataclass
class ParsedTranscript:
    tool_calls: list[ToolCall] = field(default_factory=list)
    user_texts: list[str] = field(default_factory=list)
    user_events: list[tuple[int, str]] = field(default_factory=list)


def _blocks(obj: dict) -> list:
    content = (obj.get("message") or {}).get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def parse_transcript(path: str) -> ParsedTranscript:
    out = ParsedTranscript()
    by_id: dict[str, ToolCall] = {}
    seq = 0
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = (obj.get("message") or {}).get("role")
            for b in _blocks(obj):
                if not isinstance(b, dict):
                    continue
                btype = b.get("type")
                if btype == "tool_use":
                    call = ToolCall(id=b.get("id", ""), name=b.get("name", ""), input=b.get("input") or {}, seq=seq)
                    seq += 1
                    out.tool_calls.append(call)
                    if call.id:
                        by_id[call.id] = call
                elif btype == "tool_result":
                    call = by_id.get(b.get("tool_use_id", ""))
                    if call is not None:
                        call.is_error = bool(b.get("is_error", False))
                        call.result_text = str(b.get("content", ""))[:_CLIP]
                elif btype == "text" and role == "user":
                    text = (b.get("text") or "").strip()
                    if text:
                        out.user_texts.append(text)
                        out.user_events.append((seq, text))
                        seq += 1
    return out
