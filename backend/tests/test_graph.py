# ============================================================
# AgAI_31: End-to-End Graph Test
# ============================================================

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.graph import run_graph


def test_billing_query():
    print("\n=== TEST 1: Billing Query ===")
    result = run_graph(
        user_message="What is my current account status and latest invoice?",
        customer_id="cust_001",
    )
    print(f"Intent:       {result['intent']}")
    print(f"Outcome:      {result['outcome']}")
    print(f"Response:     {result['response'][:200]}")
    print(f"Eval Scores:  {result['eval_scores']}")
    print(f"Cost USD:     {result['total_cost_usd']}")
    print(f"Latency MS:   {result['total_latency_ms']}")
    print(f"Citations:    {result['citations']}")
    print(f"Errors:       {result['errors']}")
    assert result["intent"] == "billing_query", f"Expected billing_query, got {result['intent']}"
    assert result["response"], "Response should not be empty"
    print("PASSED")


def test_refund_request():
    print("\n=== TEST 2: Refund Request ===")
    result = run_graph(
        user_message="I was charged twice in January 2025. I need a refund for the duplicate charge.",
        customer_id="cust_001",
    )
    print(f"Intent:            {result['intent']}")
    print(f"Outcome:           {result['outcome']}")
    print(f"Response:          {result['response'][:200]}")
    print(f"Pending Approvals: {result['pending_approvals']}")
    print(f"Eval Scores:       {result['eval_scores']}")
    print(f"Errors:            {result['errors']}")
    assert result["intent"] == "refund_request", f"Expected refund_request, got {result['intent']}"
    print("PASSED")


def test_policy_check():
    print("\n=== TEST 3: Policy Check ===")
    result = run_graph(
        user_message="What is your refund policy for duplicate charges?",
        customer_id="cust_002",
    )
    print(f"Intent:       {result['intent']}")
    print(f"Outcome:      {result['outcome']}")
    print(f"Response:     {result['response'][:200]}")
    print(f"Citations:    {result['citations']}")
    print(f"Eval Scores:  {result['eval_scores']}")
    print(f"Errors:       {result['errors']}")
    assert result["intent"] == "policy_check", f"Expected policy_check, got {result['intent']}"
    print("PASSED")


def test_escalation():
    print("\n=== TEST 4: Escalation ===")
    result = run_graph(
        user_message="I want to speak to a manager immediately. This is unacceptable.",
        customer_id="cust_003",
    )
    print(f"Intent:            {result['intent']}")
    print(f"Outcome:           {result['outcome']}")
    print(f"Response:          {result['response'][:200]}")
    print(f"Pending Approvals: {result['pending_approvals']}")
    print(f"Eval Scores:       {result['eval_scores']}")
    print(f"Errors:            {result['errors']}")
    assert result["intent"] == "escalation", f"Expected escalation, got {result['intent']}"
    print("PASSED")


if __name__ == "__main__":
    test_billing_query()
    test_refund_request()
    test_policy_check()
    test_escalation()
    print("\n=== ALL TESTS PASSED ===")