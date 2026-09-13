"""
tsai_client.py -- thin client for TypeSafe.ai's POST /v1/systemone
(OPTION_A_BUILD_SPEC.md sec 3). One responsibility: send state+questions,
return a typed result with a response-freshness check. No decision logic,
no guardrail logic -- that's guardrail.py's job, this is transport only.
"""
import os
import time
import json
from pathlib import Path
from typing import Optional

import requests

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_api_key() -> str:
    key = os.environ.get("TYPESAFE_AI_API_KEY")
    if key:
        return key
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("TYPESAFE_AI_API_KEY="):
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    raise RuntimeError(
        "TYPESAFE_AI_API_KEY not set (checked env and .env at repo root)"
    )


class SystemOneClient:
    """One call = one cycle's bundled questions against one state object
    (BUILD_SPEC sec 5: "One /v1/systemone call per cycle"). Never call
    this more than once per cycle -- bundle all of that cycle's
    questions into a single `ask()`."""

    def __init__(self, api_key: Optional[str] = None, timeout_s: float = 8.0,
                 freshness_s: float = 3.0):
        self.api_key = api_key or _load_api_key()
        self.timeout_s = timeout_s
        # freshness_s: max acceptable round-trip latency before a response
        # is treated as stale (BUILD_SPEC sec 6 -- "check response
        # freshness before applying a result to a changed situation").
        # 3s is a conservative placeholder for a ~1-2Hz control cycle;
        # tighten/loosen per real dry-run latency (BUILD_LOG.md).
        self.freshness_s = freshness_s

    def ask(self, state: dict, questions: dict) -> dict:
        """Returns:
        {
          "ok": bool,                 # transport succeeded and JSON parsed
          "stale": bool,               # round-trip exceeded freshness_s
          "latency_s": float,
          "answers": {question_name: {...}} | None,
          "error": str | None,
        }
        Never raises -- every failure mode (timeout, non-200, bad JSON,
        malformed per-question payload) is returned as ok=False with a
        typed `error`, so pilot_loop.py's watchdog can count it as a
        missed cycle (BUILD_SPEC sec 6) instead of crashing the loop.
        """
        request_t = time.time()
        try:
            resp = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": MODEL, "state": state, "questions": questions},
                timeout=self.timeout_s,
            )
        except requests.exceptions.RequestException as e:
            return {"ok": False, "stale": False, "latency_s": time.time() - request_t,
                    "answers": None, "error": f"request_failed: {e}"}

        latency_s = time.time() - request_t

        if resp.status_code != 200:
            return {"ok": False, "stale": False, "latency_s": latency_s,
                    "answers": None,
                    "error": f"http_{resp.status_code}: {resp.text[:300]}"}

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            return {"ok": False, "stale": False, "latency_s": latency_s,
                    "answers": None, "error": "invalid_json_response"}

        if not isinstance(data, dict):
            return {"ok": False, "stale": False, "latency_s": latency_s,
                    "answers": None, "error": f"unexpected_response_shape: {type(data)}"}

        stale = latency_s > self.freshness_s
        return {"ok": True, "stale": stale, "latency_s": latency_s,
                "answers": data, "error": None}


if __name__ == "__main__":
    client = SystemOneClient()
    demo_state = {"cycle_id": 0, "t": 0.0, "phase": "SELF_TEST",
                  "vehicle": {"altitude_m": 100.0}}
    demo_questions = {"throttle_action": {
        "type": "choice",
        "instructions": "Self-test call, pick 'hold'.",
        "criteria": {"hold": "hold", "insufficient_data": "n/a"},
    }}
    result = client.ask(demo_state, demo_questions)
    print(json.dumps(result, indent=2))
