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

MAX_ROUNDS = 20


RUN_AGENT_EVAL = os.getenv("RUN_AGENT_EVAL", "false").lower() in {"1", "true", "yes"}


def classify_difficulty(step_count: int) -> str:
    """Return the difficulty label for a task based on its estimated steps."""
    if step_count <= 5:
        return "easy"
    if step_count <= 10:
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
    # Easy (<=5 steps)
    make_task(
        "easy_example_domain",
        "Open example.com, and report the H1 text shown on the page.",
        2,
    ),
    make_task(
        "easy_python_news",
        "Search for 'Python news', and report the latest news headline shown on the homepage.",
        5,
    ),
    make_task(
        "easy_bing_time",
        "Go to bing.com, search for 'current time in Tokyo', and report the time displayed in the result widget.",
        4,
    ),
    make_task(
        "easy_github_signup",
        "Search for 'GitHub' on DuckDuckGo, open github.com, and report the text of the 'Sign up' button in the header.",
        5,
    ),
    make_task(
        "easy_wikipedia_ai",
        "Open wikipedia.org, search for 'Artificial Intelligence', and report the first sentence of the summary.",
        5,
    ),
    make_task(
        "easy_stackoverflow_top",
        "Search for 'Stack Overflow' on DuckDuckGo, open the website, and report the title of the top question in the 'Top Questions' list.",
        5,
    ),
    make_task(
        "easy_weather_ny",
        "Go to weather.com, search for 'New York', and report the current temperature.",
        5,
    ),
    make_task(
        "easy_hackernews_top",
        "Search for 'Hacker News' on DuckDuckGo, open news.ycombinator.com, and report the title of the number 1 post.",
        5,
    ),
    make_task(
        "easy_w3c_news",
        "Search for 'W3C' on DuckDuckGo, open w3.org, and report the text of the first news item.",
        5,
    ),
    make_task(
        "easy_react_heading",
        "Search for 'React' on DuckDuckGo, open react.dev, and report the main heading on the landing page.",
        5,
    ),
    # Medium (6-10 steps)
    make_task(
        "medium_bilibili_anime",
        "Search for \"bilibili\", open the bilibili website, type and search for the most popular anime, and give a like.",
        10,
    ),
    make_task(
        "medium_imdb_scifi",
        "Search for 'best sci-fi movies 2024' on DuckDuckGo, open an IMDB list result, sort by rating if possible, and list the top 3 movies with their ratings.",
        9,
    ),
    make_task(
        "medium_amazon_keyboard",
        "Go to amazon.com, search for 'mechanical keyboard', filter by '4 stars & up', open the first result, and report the price and product title.",
        10,
    ),
    make_task(
        "medium_recipe_cake",
        "Search for 'recipe for chocolate cake' on DuckDuckGo, open a recipe from a major site, scroll to the ingredients list, and save the ingredients text to a file.",
        9,
    ),
    make_task(
        "medium_github_vscode_issue",
        "Navigate to github.com/microsoft/vscode, go to the 'Issues' tab, filter by 'bug' label, and report the title of the most recently updated open bug.",
        8,
    ),
    # Hard (>10 steps)
    make_task(
        "hard_paper_attention",
        "Find the paper 'Attention is all you need', summarize the content, save all the images in the paper, then interpret the first image by explaining the process it shows.",
        13,
    ),
    make_task(
        "hard_spacex_history",
        "Search for 'SpaceX Starship' on Wikipedia, find the launch history table, extract the date and outcome of the last 3 test flights, and summarize the progress in a short paragraph.",
        12,
    ),
    make_task(
        "hard_arxiv_llm",
        "Go to arxiv.org, search for 'Large Language Models', sort by submission date, open the most recent paper's PDF, take a screenshot of the abstract, and summarize the abstract text.",
        12,
    ),
    make_task(
        "hard_housing_london",
        "Search for 'housing prices in London' on a real estate site, search for a specific area, filter by price range, open the first 3 listings, and create a comparison table of price, location, and number of bedrooms.",
        14,
    ),
    make_task(
        "hard_tech_news_summary",
        "Search for 'latest tech news' on TechCrunch, open the top 3 articles, summarize each one in 2 sentences, and identify a common theme across them.",
        15,
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
            "easy": {"total": 0, "success": 0, "duration_seconds": 0.0},
            "medium": {"total": 0, "success": 0, "duration_seconds": 0.0},
            "hard": {"total": 0, "success": 0, "duration_seconds": 0.0},
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

            per_difficulty[difficulty]["duration_seconds"] += round(duration, 2)
            with open(self.artifacts_root / "per_difficulty.json", "w", encoding="utf-8") as f:
                json.dump(per_difficulty, f, ensure_ascii=False, indent=4)

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
            agent.close_session()

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
