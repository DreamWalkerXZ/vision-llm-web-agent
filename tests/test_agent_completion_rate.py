"""Integration-style completion rate evaluator for the Vision-LLM Web Agent.

This module defines a pytest guard that can spin up the real web agent, feed it
20 curated tasks (10 easy, 5 medium, 5 hard), and measure how often it manages
to finish the instructions. The browser stays visible (non-headless) because the
agent reuses the same toolchain as `main.py`.

Usage (PowerShell):

    $env:RUN_AGENT_EVAL=1; uv run pytest tests/test_agent_completion_rate.py -k completion_rate

Only enable the run flag when you actually want to watch the browser; otherwise
this test is skipped automatically so that CI stays fast.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest

from vision_llm_web_agent.agent_controller import Agent
from vision_llm_web_agent.vllm_client import VLLMClient
from vision_llm_web_agent.config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_LANGUAGE_MODEL,
    MAX_ROUNDS,
    TIMEOUT_PER_ROUND,
    ARTIFACTS_DIR,
)


RUN_AGENT_EVAL = os.getenv("RUN_AGENT_EVAL", "false").lower() in {"1", "true", "yes"}


def classify_difficulty(step_count: int) -> str:
    """Return the difficulty label for a task based on its estimated steps."""
    if step_count <= 4:
        return "easy"
    if step_count <= 8:
        return "medium"
    return "hard"


@dataclass(frozen=True)
class EvaluationTask:
    """Represents a single evaluation prompt for the agent."""

    id: str
    prompt: str
    estimated_steps: int

    @property
    def difficulty(self) -> str:
        return classify_difficulty(self.estimated_steps)


def make_task(task_id: str, prompt: str, estimated_steps: int) -> EvaluationTask:
    """Helper for concise task definitions."""
    return EvaluationTask(id=task_id, prompt=prompt, estimated_steps=estimated_steps)


EVALUATION_TASKS: List[EvaluationTask] = [
    # Easy (<=4 steps)
    make_task(
        "easy_example_domain",
        "Use DuckDuckGo to search for 'Example Domain', open example.com, and report the H1 text shown on the page.",
        4,
    ),
    make_task(
        "easy_iana_reserved",
        "Search for 'IANA reserved domains', open the official IANA page, and list the three example domains that it highlights.",
        4,
    ),
    make_task(
        "easy_python_download",
        "Use DuckDuckGo to locate the Python.org downloads page and report the text of the large download button shown near the hero banner.",
        4,
    ),
    make_task(
        "easy_wikipedia_hku_motto",
        "Open the Wikipedia article for 'University of Hong Kong' and summarize the motto text shown in the infobox.",
        4,
    ),
    make_task(
        "easy_mdn_flexbox",
        "Find the MDN Web Docs page titled 'Basic concepts of flexbox' and provide the main heading text shown on that page.",
        4,
    ),
    make_task(
        "easy_openai_blog",
        "Search for 'OpenAI research blog', open blog.openai.com, and report the title of the top-most article visible on the landing page.",
        4,
    ),
    make_task(
        "easy_duckduckgo_weather_hk",
        "Ask DuckDuckGo for the current weather in Hong Kong and report the temperature shown in the instant answer card.",
        3,
    ),
    make_task(
        "easy_github_copilot_cta",
        "Search for 'GitHub Copilot', open the official product page on github.com/features/copilot, and capture the label of the primary call-to-action button.",
        4,
    ),
    make_task(
        "easy_mdn_fetch",
        "Locate the MDN documentation for the JavaScript Fetch API and provide the short description that appears directly under the title.",
        4,
    ),
    make_task(
        "easy_wikipedia_playwright",
        "Open Wikipedia's article about Playwright (software) and summarize in one sentence what the tool is.",
        4,
    ),
    # Medium (5-8 steps)
    make_task(
        "medium_sdgs_goal17",
        "Search for 'Sustainable Development Goals', open the Wikipedia article, scroll to the goals list, and extract the text of Goal 17.",
        6,
    ),
    make_task(
        "medium_pep8_consistency",
        "Find 'PEP 8 - Style Guide for Python Code' on peps.python.org, navigate to the 'A Foolish Consistency is the Hobgoblin of Little Minds' section, and quote the first principle bullet listed there.",
        6,
    ),
    make_task(
        "medium_playwright_release",
        "Go to the GitHub repository microsoft/playwright, open the Releases tab, and report the latest release tag along with its publication date.",
        7,
    ),
    make_task(
        "medium_mdn_css_grid",
        "Use DuckDuckGo to find the MDN 'CSS Grid Layout' guide, jump to the 'Line-based placement' section, and summarize the first paragraph in your own words.",
        6,
    ),
    make_task(
        "medium_hktram_fares",
        "Open the Wikipedia page for 'Hong Kong Tramways', scroll to the 'Fares' section, and report the adult fare stated there.",
        6,
    ),
    # Hard (>=9 steps)
    make_task(
        "hard_hong_kong_currency",
        "Open the Wikipedia article for 'Hong Kong', capture the GDP (nominal) figure from the infobox, then follow the 'Hong Kong dollar' link and list the banknote denominations mentioned; conclude with a comparison of GDP versus the largest banknote.",
        10,
    ),
    make_task(
        "hard_playwright_release_compare",
        "Starting from DuckDuckGo, find the GitHub repos 'microsoft/playwright' and 'microsoft/playwright-python'. Record the latest release tag for each and conclude with a sentence comparing the two versions.",
        11,
    ),
    make_task(
        "hard_python_asyncio_walk",
        "Navigate to python.org, open the documentation for 'asyncio', follow the 'Event Loop' section, list the responsibilities bullets, then follow the 'Coroutines and Tasks' link and summarize its opening paragraph.",
        10,
    ),
    make_task(
        "hard_mdn_web_speech",
        "Search for 'Web Speech API MDN', open the article, scroll to the 'Using the Web Speech API' section to list the two main interfaces, then review the 'Basic examples: Recognition' subsection and describe what the demo button triggers.",
        9,
    ),
    make_task(
        "hard_world_heritage_hk",
        "Use DuckDuckGo to find the 'List of UNESCO World Heritage Sites in China' on Wikipedia, count how many entries mention Hong Kong, then follow the 'Hong Kong UNESCO Global Geopark' entry to confirm the year it was inscribed.",
        10,
    ),
]


EXPECTED_TASK_SPLIT = {"easy": 10, "medium": 5, "hard": 5}


def _validate_task_distribution(tasks: List[EvaluationTask]) -> None:
    counts = {"easy": 0, "medium": 0, "hard": 0}
    for task in tasks:
        counts[task.difficulty] += 1
    for difficulty, expected in EXPECTED_TASK_SPLIT.items():
        actual = counts[difficulty]
        if actual != expected:
            raise ValueError(
                f"Expected {expected} {difficulty} tasks but found {actual}. Please adjust `EVALUATION_TASKS`."
            )


_validate_task_distribution(EVALUATION_TASKS)


ROUNDS_BY_DIFFICULTY = {"easy": MAX_ROUNDS-12, "medium": MAX_ROUNDS-6, "hard": MAX_ROUNDS}


class AgentCompletionEvaluator:
    """Runs the full-suite evaluation and aggregates completion metrics."""

    def __init__(self, tasks: List[EvaluationTask]):
        if not tasks:
            raise ValueError("No evaluation tasks provided")
        self.tasks = tasks
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.artifacts_root = ARTIFACTS_DIR / "completion_evals" / self.session_id
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.summary_path = self.artifacts_root / "summary.json"

    def run(self) -> Dict[str, object]:
        if not OPENAI_API_KEY or OPENAI_API_KEY in {"", "EMPTY", "test-key"}:
            raise RuntimeError("OPENAI_API_KEY is missing or invalid; cannot run evaluation.")

        vllm_client = VLLMClient(
            base_url=OPENAI_BASE_URL,
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            language_model=OPENAI_LANGUAGE_MODEL,
        )

        if not vllm_client.test_connection():
            raise RuntimeError("Failed to connect to the Vision LLM API; aborting evaluation run.")

        per_difficulty = {
            "easy": {"total": 0, "success": 0},
            "medium": {"total": 0, "success": 0},
            "hard": {"total": 0, "success": 0},
        }
        task_results = []
        started_at = datetime.utcnow().isoformat()
        wall_clock_start = time.time()

        for task in self.tasks:
            difficulty = task.difficulty
            per_difficulty[difficulty]["total"] += 1
            round_limit = min(ROUNDS_BY_DIFFICULTY[difficulty], MAX_ROUNDS)
            task_dir = self.artifacts_root / f"{task.id}_{difficulty}"
            task_dir.mkdir(parents=True, exist_ok=True)

            agent = Agent(
                vllm_client=vllm_client,
                max_rounds=round_limit,
                timeout_per_round=TIMEOUT_PER_ROUND,
                artifacts_dir=str(task_dir),
            )

            print("\n" + "=" * 80)
            print(f"Starting task {task.id} ({difficulty})")
            print(task.prompt)
            print("=" * 80 + "\n")

            start_time = time.time()
            try:
                final_answer = agent.execute(task.prompt)
            except Exception as exc:  # pragma: no cover - guard rail for unexpected crashes
                final_answer = f"[ERROR] Exception while executing task {task.id}: {exc}"
            duration = time.time() - start_time
            success = self._did_succeed(final_answer)

            if success:
                per_difficulty[difficulty]["success"] += 1

            task_results.append(
                {
                    "task_id": task.id,
                    "prompt": task.prompt,
                    "difficulty": difficulty,
                    "estimated_steps": task.estimated_steps,
                    "round_limit": round_limit,
                    "duration_seconds": round(duration, 2),
                    "success": success,
                    "final_answer": final_answer,
                    "artifact_dir": str(task_dir),
                }
            )

        ended_at = datetime.utcnow().isoformat()
        total_duration = round(time.time() - wall_clock_start, 2)
        summary = self._build_summary(task_results, per_difficulty, started_at, ended_at, total_duration)
        self._write_summary(summary)
        self._print_summary(summary)
        return summary

    @staticmethod
    def _did_succeed(final_answer: str) -> bool:
        if not final_answer:
            return False
        normalized = final_answer.lower()
        failure_markers = [
            "task incomplete",
            "fatal error",
            "[error]",
            "failed",
            "error:",
        ]
        return not any(marker in normalized for marker in failure_markers)

    def _build_summary(
        self,
        task_results: List[Dict[str, object]],
        per_difficulty: Dict[str, Dict[str, int]],
        started_at: str,
        ended_at: str,
        total_duration: float,
    ) -> Dict[str, object]:
        def rate(success: int, total: int) -> float:
            return round(success / total, 3) if total else 0.0

        overall_success = sum(bucket["success"] for bucket in per_difficulty.values())
        overall_total = len(self.tasks)
        breakdown = {
            difficulty: {
                "total": bucket["total"],
                "success": bucket["success"],
                "completion_rate": rate(bucket["success"], bucket["total"]),
            }
            for difficulty, bucket in per_difficulty.items()
        }
        return {
            "session_id": self.session_id,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": total_duration,
            "total_tasks": overall_total,
            "overall_completion_rate": rate(overall_success, overall_total),
            "difficulty_breakdown": breakdown,
            "tasks": task_results,
            "summary_path": str(self.summary_path),
        }

    def _write_summary(self, summary: Dict[str, object]) -> None:
        with self.summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False)
        print(f"Saved evaluation summary to {self.summary_path}")

    @staticmethod
    def _print_summary(summary: Dict[str, object]) -> None:
        print("\n" + "#" * 80)
        print("COMPLETION SUMMARY")
        print("#" * 80)
        print(f"Session: {summary['session_id']}")
        print(f"Duration: {summary['duration_seconds']}s for {summary['total_tasks']} tasks")
        print(f"Overall completion rate: {summary['overall_completion_rate'] * 100:.1f}%")
        for difficulty, stats in summary["difficulty_breakdown"].items():
            print(
                f" - {difficulty.title():<6}: {stats['success']}/{stats['total']} "
                f"({stats['completion_rate'] * 100:.1f}%)"
            )
        print("Summary JSON:", summary["summary_path"])
        print("#" * 80 + "\n")


def _can_run_eval() -> bool:
    return RUN_AGENT_EVAL


@pytest.mark.skipif(not _can_run_eval(), reason="Set RUN_AGENT_EVAL=1 to enable the browser completion test.")
def test_agent_completion_rate():
    """Runs the 20-task benchmark and asserts the bookkeeping succeeded."""
    evaluator = AgentCompletionEvaluator(EVALUATION_TASKS)
    summary = evaluator.run()
    assert summary["total_tasks"] == len(EVALUATION_TASKS)
    for difficulty, expected in EXPECTED_TASK_SPLIT.items():
        assert summary["difficulty_breakdown"][difficulty]["total"] == expected


if __name__ == "__main__":  # pragma: no cover
    if not _can_run_eval():
        raise SystemExit("Set RUN_AGENT_EVAL=1 before running this module directly.")
    evaluator = AgentCompletionEvaluator(EVALUATION_TASKS)
    evaluator.run()
