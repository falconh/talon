"""Attribute friction to each detected plugin over its activity window, so a plugin that
behaved cleanly no longer inherits friction caused elsewhere in the same session."""
from __future__ import annotations

from transcript import ParsedTranscript, ToolCall
from friction import scan_friction
from detect import domain_match_seqs


def _plugin_of_skill(c: ToolCall) -> str:
    return str(c.input.get("skill", "")).split(":", 1)[0]


def _under_spans(under: set[str], calls: list[ToolCall],
                 domain_map: dict[str, dict]) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for p in under:
        seqs = domain_match_seqs(calls, domain_map.get(p, {}))
        if seqs:
            spans[p] = (min(seqs), max(seqs))
    return spans


def per_plugin_friction(parsed: ParsedTranscript, used: set[str], under: set[str],
                        domain_map: dict[str, dict]) -> dict[str, dict]:
    calls = parsed.tool_calls
    skill_seqs = [c.seq for c in calls if c.name == "Skill"]
    spans = _under_spans(under, calls, domain_map)
    span_starts = [lo for (lo, _hi) in spans.values()]
    out: dict[str, dict] = {}
    for plugin in used | under:
        if plugin in used:
            start = min(c.seq for c in calls
                        if c.name == "Skill" and _plugin_of_skill(c) == plugin)
            # Window-end boundaries are only those AFTER the skill call; a domain span
            # already in progress before the skill isn't a boundary, so its post-skill
            # errors fall in this window too (the under-trigger plugin still gets them).
            ends = [s for s in skill_seqs if s > start] + [s for s in span_starts if s > start]
            end = min(ends) if ends else None  # None -> open to end of session
            in_window = (lambda s, lo=start, hi=end: s >= lo and (hi is None or s < hi))
        else:
            span = spans.get(plugin)
            if span is None:
                out[plugin] = scan_friction([], []).as_dict()
                continue
            in_window = (lambda s, lo=span[0], hi=span[1]: lo <= s <= hi)
        wcalls = [c for c in calls if in_window(c.seq)]
        wtexts = [t for (sq, t) in parsed.user_events if in_window(sq)]
        out[plugin] = scan_friction(wcalls, wtexts).as_dict()
    return out
