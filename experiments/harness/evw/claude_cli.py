"""Lean headless Claude calls through the Claude Code CLI on the user's subscription, with a usage ledger.

Every call appends one JSON line to the ledger (tokens per model and the list-price cost equivalent reported by the
CLI), so experiment cost can be reported and the weekly share of the plan can be tracked.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

LEDGER = Path(os.environ.get("EVW_LEDGER", Path(__file__).resolve().parents[2] / "pilot" / "usage_ledger.jsonl"))


class ClaudeError(RuntimeError):
    pass


def ask(prompt: str, *, system: str, model: str = "haiku", effort: str | None = None, tag: str = "",
        timeout: int = 900, retries: int = 2) -> str:
    """One stateless call with no tools, no settings, no MCP. Returns the text result."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # never bill an API key
    cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--max-turns", "1",
           "--system-prompt", system, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
           "--disable-slash-commands", "--no-session-persistence"]
    if effort:
        cmd += ["--effort", effort]
    last = None
    for attempt in range(retries + 1):
        t0 = time.time()
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
        try:
            d = json.loads(p.stdout)
        except json.JSONDecodeError:
            last = ClaudeError(f"bad output (rc={p.returncode}): {p.stdout[:300]} {p.stderr[:300]}")
            time.sleep(5 * (attempt + 1))
            continue
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(json.dumps({"t": time.time(), "tag": tag, "model": model, "effort": effort,
                                "secs": round(time.time() - t0, 1), "cost_usd_list": d.get("total_cost_usd"),
                                "modelUsage": d.get("modelUsage"), "is_error": d.get("is_error")}) + "\n")
        if d.get("is_error"):
            last = ClaudeError(str(d.get("result"))[:300])
            time.sleep(10 * (attempt + 1))
            continue
        return d.get("result") or ""
    raise last or ClaudeError("unknown failure")


def ledger_summary(tag_prefix: str = "") -> dict:
    tot = {"calls": 0, "cost_usd_list": 0.0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    if not LEDGER.exists():
        return tot
    for line in LEDGER.open():
        r = json.loads(line)
        if not r.get("tag", "").startswith(tag_prefix):
            continue
        tot["calls"] += 1
        tot["cost_usd_list"] += r.get("cost_usd_list") or 0
        for mu in (r.get("modelUsage") or {}).values():
            tot["input"] += mu.get("inputTokens", 0)
            tot["output"] += mu.get("outputTokens", 0)
            tot["cache_read"] += mu.get("cacheReadInputTokens", 0)
            tot["cache_write"] += mu.get("cacheCreationInputTokens", 0)
    return tot
