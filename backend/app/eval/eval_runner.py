# ============================================================
# AgAI_31: Eval Runner — Offline + Regression Testing
# ============================================================

import json
import os
import time
import uuid
import asyncio
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger()

# ============================================================
# PATHS
# ============================================================

ROOT_DIR = Path(__file__).resolve().parents[4]  # AgAI_31_Multi_Agent_Eval_Platform/
EVAL_DATA_PATH = ROOT_DIR / "eval_data" / "test_cases.json"
REPORTS_DIR = ROOT_DIR / "eval_data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# SCORING HELPERS
# ============================================================

def score_intent(actual: str, expected: str) -> float:
    """1.0 if intent matches exactly, 0.0 otherwise."""
    return 1.0 if actual.strip().lower() == expected.strip().lower() else 0.0


def score_tool_calls(actual_tools: list[str], expected_tools: list[str]) -> float:
    """
    Partial credit scoring for tool calls.
    Full credit if all expected tools were called.
    Partial credit proportional to overlap.
    1.0 if no tools expected and none called.
    """
    if not expected_tools:
        # No tools expected — penalise if tools were called unexpectedly
        return 1.0 if not actual_tools else 0.5

    if not actual_tools:
        return 0.0

    expected_set = set(t.lower() for t in expected_tools)
    actual_set = set(t.lower() for t in actual_tools)
    overlap = expected_set & actual_set
    return len(overlap) / len(expected_set)


def score_grounding(actual_response: str, expected_sources: list[str]) -> float:
    """
    Checks whether the response references expected grounding sources.
    Looks for source keywords in the response text.
    1.0 if no sources expected (general/escalation intents).
    """
    if not expected_sources:
        return 1.0

    response_lower = actual_response.lower()
    hits = sum(1 for src in expected_sources if src.lower() in response_lower)
    return hits / len(expected_sources)


def score_escalation(actual_escalated: bool, expected_escalation: bool) -> float:
    """1.0 if escalation decision matches, 0.0 otherwise."""
    return 1.0 if actual_escalated == expected_escalation else 0.0


def score_policy_compliance(
    actual_response: str,
    expected_policy_mentioned: bool,
    intent: str,
) -> float:
    """
    For policy/refund intents, check whether response contains policy language.
    For other intents, compliance is assumed 1.0.
    """
    policy_intents = {"refund_request", "policy_check", "duplicate_charge"}
    if intent not in policy_intents:
        return 1.0

    policy_keywords = [
        "policy", "terms", "refund", "eligible", "within", "days",
        "sla", "processing", "approve", "cannot", "not eligible",
    ]
    response_lower = actual_response.lower()
    hits = sum(1 for kw in policy_keywords if kw in response_lower)
    # At least 2 policy keywords = compliant
    return min(hits / 2, 1.0)


def compute_case_scores(
    test_case: dict,
    result: dict,
    latency_ms: float,
    token_cost: float,
) -> dict:
    """
    Compute all 5 dimension scores for one test case.
    Returns a score dict with individual scores + composite task_success.
    """
    expected_intent = test_case.get("expected_intent", "")
    expected_tools = test_case.get("expected_tool_calls", [])
    expected_sources = test_case.get("expected_grounding_sources", [])
    expected_escalation = test_case.get("expected_escalation", False)

    actual_intent = result.get("intent", "")
    actual_response = result.get("final_response", "")
    actual_tools = result.get("tool_calls_made", [])
    actual_escalated = result.get("escalated", False)
    had_error = bool(result.get("errors"))

    intent_score = score_intent(actual_intent, expected_intent)
    tool_score = score_tool_calls(actual_tools, expected_tools)
    grounding_score = score_grounding(actual_response, expected_sources)
    escalation_score = score_escalation(actual_escalated, expected_escalation)
    policy_score = score_policy_compliance(actual_response, True, expected_intent)

    # Composite task success: weighted average
    # Intent routing is the most critical signal
    task_success = (
        intent_score * 0.30
        + tool_score * 0.25
        + grounding_score * 0.20
        + policy_score * 0.15
        + escalation_score * 0.10
    )

    # Error penalty: deduct 0.3 from task success if the run had errors
    if had_error:
        task_success = max(0.0, task_success - 0.30)

    return {
        "intent_score": round(intent_score, 4),
        "tool_correctness": round(tool_score, 4),
        "grounding_accuracy": round(grounding_score, 4),
        "policy_compliance": round(policy_score, 4),
        "escalation_correctness": round(escalation_score, 4),
        "task_success": round(task_success, 4),
        "latency_ms": round(latency_ms, 1),
        "token_cost_usd": round(token_cost, 6),
        "had_error": had_error,
    }


# ============================================================
# SINGLE CASE RUNNER
# ============================================================

async def run_single_case(test_case: dict, model_override: Optional[str] = None) -> dict:
    """
    Execute one test case through the live agent graph.
    Returns the graph result dict + timing.
    """
    from app.agents.graph import run_graph  # deferred import to avoid circular

    conversation_id = str(uuid.uuid4())
    message = test_case["input_message"]

    start = time.perf_counter()
    try:
        result = await run_graph(
            user_message=message,
            conversation_id=conversation_id,
        )
    except Exception as e:
        logger.error("eval_case_error", case_id=test_case.get("id"), error=str(e))
        result = {
            "intent": "unknown",
            "final_response": "",
            "tool_calls_made": [],
            "escalated": False,
            "errors": [{"agent": "graph", "error": str(e)}],
            "citations": [],
        }
    end = time.perf_counter()

    latency_ms = (end - start) * 1000

    # Extract tool calls made (from result state)
    tool_calls_made = result.get("tool_calls_made", [])
    if isinstance(tool_calls_made, list) and tool_calls_made:
        # Normalise: extract tool names if they are dicts
        tool_calls_made = [
            t.get("tool_name", t) if isinstance(t, dict) else t
            for t in tool_calls_made
        ]

    result["tool_calls_made"] = tool_calls_made

    # Token cost from eval_scores if present
    token_cost = 0.0
    if result.get("eval_scores") and isinstance(result["eval_scores"], dict):
        token_cost = result["eval_scores"].get("cost_usd", 0.0) or 0.0

    return result, latency_ms, token_cost


# ============================================================
# OFFLINE EVAL RUNNER
# ============================================================

async def run_offline_eval(
    prompt_version: str = "v1",
    model_version: str = "gpt-4o",
    save_report: bool = True,
) -> dict:
    """
    Run all test cases from eval_data/test_cases.json through the live graph.
    Returns a full eval report dict.
    """
    logger.info("offline_eval_start", prompt_version=prompt_version, model_version=model_version)

    # Load test cases
    with open(EVAL_DATA_PATH, "r") as f:
        data = json.load(f)
    test_cases = data.get("test_cases", data) if isinstance(data, dict) else data

    run_id = str(uuid.uuid4())
    run_timestamp = datetime.now(timezone.utc).isoformat()

    case_results = []
    all_scores = []

    for i, tc in enumerate(test_cases):
        case_id = tc.get("id", f"case_{i+1}")
        category = tc.get("category", "unknown")
        logger.info("running_case", case_id=case_id, category=category, index=i + 1, total=len(test_cases))

        result, latency_ms, token_cost = await run_single_case(tc)
        scores = compute_case_scores(tc, result, latency_ms, token_cost)

        case_result = {
            "case_id": case_id,
            "category": category,
            "input_message": tc["input_message"],
            "expected_intent": tc.get("expected_intent", ""),
            "actual_intent": result.get("intent", ""),
            "expected_tool_calls": tc.get("expected_tool_calls", []),
            "actual_tool_calls": result.get("tool_calls_made", []),
            "final_response_preview": (result.get("final_response", "") or "")[:200],
            "scores": scores,
            "had_error": scores["had_error"],
        }
        case_results.append(case_result)
        all_scores.append(scores)

        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)

    # ---- Aggregate metrics ----
    def avg(field):
        vals = [s[field] for s in all_scores]
        return round(statistics.mean(vals), 4) if vals else 0.0

    # Per-category breakdown
    categories = {}
    for cr in case_results:
        cat = cr["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(cr["scores"]["task_success"])

    category_summary = {
        cat: round(statistics.mean(scores), 4)
        for cat, scores in categories.items()
    }

    # Failed cases
    failed_cases = [cr for cr in case_results if cr["scores"]["task_success"] < 0.60]

    report = {
        "run_id": run_id,
        "timestamp": run_timestamp,
        "prompt_version": prompt_version,
        "model_version": model_version,
        "total_cases": len(test_cases),
        "passed": len([cr for cr in case_results if cr["scores"]["task_success"] >= 0.60]),
        "failed": len(failed_cases),
        "aggregate_metrics": {
            "task_success_rate": avg("task_success"),
            "grounding_accuracy": avg("grounding_accuracy"),
            "tool_correctness": avg("tool_correctness"),
            "policy_compliance": avg("policy_compliance"),
            "escalation_correctness": avg("escalation_correctness"),
            "avg_latency_ms": avg("latency_ms"),
            "avg_token_cost_usd": avg("token_cost_usd"),
            "error_rate": round(len([s for s in all_scores if s["had_error"]]) / len(all_scores), 4),
        },
        "category_breakdown": category_summary,
        "failed_cases": [
            {
                "case_id": fc["case_id"],
                "category": fc["category"],
                "task_success": fc["scores"]["task_success"],
                "actual_intent": fc["actual_intent"],
                "expected_intent": fc["expected_intent"],
            }
            for fc in failed_cases
        ],
        "case_results": case_results,
    }

    if save_report:
        report_path = REPORTS_DIR / f"eval_report_{run_id[:8]}_{prompt_version}_{model_version}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info("report_saved", path=str(report_path))
        report["report_path"] = str(report_path)

    return report


# ============================================================
# REGRESSION TESTING
# ============================================================

async def run_regression_test(
    baseline_report_path: str,
    new_prompt_version: str,
    new_model_version: str,
) -> dict:
    """
    Run the full offline eval with a new prompt/model version and compare
    aggregate metrics against a saved baseline report.
    Returns a regression comparison dict.
    """
    logger.info(
        "regression_test_start",
        new_prompt=new_prompt_version,
        new_model=new_model_version,
        baseline=baseline_report_path,
    )

    # Load baseline
    with open(baseline_report_path, "r") as f:
        baseline = json.load(f)

    # Run new eval
    new_report = await run_offline_eval(
        prompt_version=new_prompt_version,
        model_version=new_model_version,
        save_report=True,
    )

    # Compare aggregate metrics
    baseline_metrics = baseline["aggregate_metrics"]
    new_metrics = new_report["aggregate_metrics"]

    deltas = {}
    for metric, new_val in new_metrics.items():
        old_val = baseline_metrics.get(metric, 0.0)
        delta = round(new_val - old_val, 4)
        # For latency and cost, lower is better; for others higher is better
        if metric in ("avg_latency_ms", "avg_token_cost_usd", "error_rate"):
            improved = delta < 0
        else:
            improved = delta > 0

        deltas[metric] = {
            "baseline": old_val,
            "new": new_val,
            "delta": delta,
            "improved": improved,
        }

    # Summary verdict
    key_metrics = ["task_success_rate", "grounding_accuracy", "tool_correctness"]
    improvements = sum(1 for m in key_metrics if deltas[m]["improved"])
    regressions = sum(1 for m in key_metrics if not deltas[m]["improved"] and deltas[m]["delta"] != 0)

    if improvements > regressions:
        verdict = "IMPROVED"
    elif regressions > improvements:
        verdict = "REGRESSED"
    else:
        verdict = "NEUTRAL"

    regression_report = {
        "comparison_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_run_id": baseline["run_id"],
        "baseline_prompt_version": baseline["prompt_version"],
        "baseline_model_version": baseline["model_version"],
        "new_run_id": new_report["run_id"],
        "new_prompt_version": new_prompt_version,
        "new_model_version": new_model_version,
        "verdict": verdict,
        "metric_deltas": deltas,
        "new_report_path": new_report.get("report_path", ""),
    }

    # Save comparison report
    comp_path = REPORTS_DIR / f"regression_{regression_report['comparison_id'][:8]}.json"
    with open(comp_path, "w") as f:
        json.dump(regression_report, f, indent=2)
    regression_report["comparison_report_path"] = str(comp_path)

    logger.info("regression_complete", verdict=verdict)
    return regression_report


# ============================================================
# PRODUCTION TRACE EVAL
# ============================================================

async def eval_from_trace(conversation_id: str) -> dict:
    """
    Load a saved conversation trace from Supabase and re-score it.
    Writes updated scores back to the trace record.
    """
    from app.observability.tracer import get_supabase

    supabase = get_supabase()

    # Fetch conversation
    conv = (
        supabase.table("evals_conversations")
        .select("*")
        .eq("conversation_id", conversation_id)
        .single()
        .execute()
    )
    if not conv.data:
        raise ValueError(f"Conversation {conversation_id} not found in trace store.")

    conv_data = conv.data

    # Fetch trace steps
    steps = (
        supabase.table("evals_trace_steps")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("timestamp")
        .execute()
    )

    # Reconstruct result dict from trace
    final_response = conv_data.get("final_response", "")
    intent = conv_data.get("intent", "unknown")
    outcome = conv_data.get("outcome", "unknown")

    tool_steps = [s for s in (steps.data or []) if s.get("step_type") == "tool_call"]
    tool_calls_made = [s.get("tool_name", "") for s in tool_steps if s.get("tool_name")]

    escalated = any("escalate" in t.lower() for t in tool_calls_made)

    result = {
        "intent": intent,
        "final_response": final_response,
        "tool_calls_made": tool_calls_made,
        "escalated": escalated,
        "errors": [] if outcome != "failed" else [{"agent": "unknown", "error": "trace outcome=failed"}],
    }

    total_latency = conv_data.get("total_latency_ms", 0) or 0
    total_cost = conv_data.get("total_cost_usd", 0) or 0

    # We don't have a test case to compare against, so we use a relaxed scoring
    pseudo_case = {
        "expected_intent": intent,  # assume saved intent was correct
        "expected_tool_calls": tool_calls_made,
        "expected_grounding_sources": [],
        "expected_escalation": escalated,
    }

    scores = compute_case_scores(pseudo_case, result, total_latency, total_cost)

    # Write scores back to trace
    supabase.table("evals_eval_results").upsert({
        "conversation_id": conversation_id,
        "eval_mode": "production_trace",
        "task_success": scores["task_success"],
        "grounding_accuracy": scores["grounding_accuracy"],
        "tool_correctness": scores["tool_correctness"],
        "policy_compliance": scores["policy_compliance"],
        "escalation_correctness": scores["escalation_correctness"],
        "latency_ms": scores["latency_ms"],
        "cost_usd": scores["token_cost_usd"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }).execute()

    return {
        "conversation_id": conversation_id,
        "scores": scores,
        "intent": intent,
        "outcome": outcome,
    }


# ============================================================
# PRETTY PRINT SUMMARY TABLE
# ============================================================

def print_summary_table(report: dict) -> None:
    """Print a formatted summary table to the terminal."""
    m = report["aggregate_metrics"]
    print("\n" + "=" * 60)
    print(f"  EVAL REPORT — {report['prompt_version']} / {report['model_version']}")
    print(f"  Run ID: {report['run_id'][:8]}  |  {report['timestamp'][:19]}")
    print("=" * 60)
    print(f"  Total Cases   : {report['total_cases']}")
    print(f"  Passed (>=60%): {report['passed']}")
    print(f"  Failed (<60%) : {report['failed']}")
    print("-" * 60)
    print(f"  Task Success Rate   : {m['task_success_rate']:.1%}")
    print(f"  Grounding Accuracy  : {m['grounding_accuracy']:.1%}")
    print(f"  Tool Correctness    : {m['tool_correctness']:.1%}")
    print(f"  Policy Compliance   : {m['policy_compliance']:.1%}")
    print(f"  Escalation Correct  : {m['escalation_correctness']:.1%}")
    print(f"  Error Rate          : {m['error_rate']:.1%}")
    print(f"  Avg Latency         : {m['avg_latency_ms']:.0f} ms")
    print(f"  Avg Token Cost      : ${m['avg_token_cost_usd']:.5f}")
    print("-" * 60)
    print("  Category Breakdown:")
    for cat, score in report["category_breakdown"].items():
        bar = "#" * int(score * 20)
        print(f"    {cat:<20} {score:.1%}  {bar}")
    if report["failed_cases"]:
        print("-" * 60)
        print("  Failed Cases:")
        for fc in report["failed_cases"]:
            print(f"    [{fc['case_id']}] {fc['category']} — success={fc['task_success']:.2f} | got={fc['actual_intent']} expected={fc['expected_intent']}")
    print("=" * 60 + "\n")


# ============================================================
# CLI ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AgAI_31 Eval Runner")
    parser.add_argument("--mode", choices=["offline", "regression", "trace"], default="offline")
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--model-version", default="gpt-4o")
    parser.add_argument("--baseline", help="Path to baseline JSON report (regression mode)")
    parser.add_argument("--conversation-id", help="Conversation ID (trace mode)")
    args = parser.parse_args()

    if args.mode == "offline":
        report = asyncio.run(run_offline_eval(
            prompt_version=args.prompt_version,
            model_version=args.model_version,
        ))
        print_summary_table(report)

    elif args.mode == "regression":
        if not args.baseline:
            print("ERROR: --baseline path required for regression mode")
        else:
            report = asyncio.run(run_regression_test(
                baseline_report_path=args.baseline,
                new_prompt_version=args.prompt_version,
                new_model_version=args.model_version,
            ))
            print(json.dumps(report["metric_deltas"], indent=2))
            print(f"\nVERDICT: {report['verdict']}")

    elif args.mode == "trace":
        if not args.conversation_id:
            print("ERROR: --conversation-id required for trace mode")
        else:
            result = asyncio.run(eval_from_trace(args.conversation_id))
            print(json.dumps(result, indent=2))