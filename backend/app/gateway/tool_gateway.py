# ============================================================
# AgAI_31: Tool Gateway — Schema Validation + HIL Approval Queue
# ============================================================

import os
import uuid
import json
import time
import structlog
from typing import Any, Optional
from datetime import datetime, timezone

import redis
from dotenv import load_dotenv
from pydantic import ValidationError

from app.schemas.models import (
    ToolCallRequest,
    ToolCallResult,
    ApprovalRequest,
    GetCustomerProfileInput,
    GetInvoiceHistoryInput,
    CheckRefundPolicyInput,
    CreateRefundTicketInput,
    EscalateToHumanInput,
)
from app.observability.tracer import get_supabase

load_dotenv()

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
APPROVAL_QUEUE_KEY = "agai31:approval_queue"

# ============================================================
# TOOL REGISTRY
# Maps tool name -> (input schema class, risk level, executor fn)
# ============================================================

TOOL_REGISTRY: dict[str, dict] = {
    "get_customer_profile": {
        "schema":     GetCustomerProfileInput,
        "risk_level": "LOW",
        "executor":   "_execute_get_customer_profile",
    },
    "get_invoice_history": {
        "schema":     GetInvoiceHistoryInput,
        "risk_level": "LOW",
        "executor":   "_execute_get_invoice_history",
    },
    "check_refund_policy": {
        "schema":     CheckRefundPolicyInput,
        "risk_level": "LOW",
        "executor":   "_execute_check_refund_policy",
    },
    "create_refund_ticket": {
        "schema":     CreateRefundTicketInput,
        "risk_level": "HIGH",
        "executor":   "_execute_create_refund_ticket",
    },
    "escalate_to_human": {
        "schema":     EscalateToHumanInput,
        "risk_level": "HIGH",
        "executor":   "_execute_escalate_to_human",
    },
}


# ============================================================
# REDIS CLIENT
# ============================================================

def get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


# ============================================================
# TOOL GATEWAY — MAIN ENTRY POINT
# ============================================================

class ToolGateway:

    def process(
        self,
        request: ToolCallRequest,
        conversation_id: str,
    ) -> ToolCallResult:
        """
        Main gateway entry point.
        1. Validate tool exists in registry
        2. Validate input schema
        3. Classify risk
        4. Execute (LOW) or queue for approval (HIGH)
        5. Log to evals_tool_calls
        """
        tool_name = request.tool_name

        # Step 1: Tool exists?
        if tool_name not in TOOL_REGISTRY:
            return self._rejected_result(
                request,
                error=f"Unknown tool: {tool_name}",
            )

        config = TOOL_REGISTRY[tool_name]
        risk_level = config["risk_level"]

        # Step 2: Schema validation
        try:
            validated_input = config["schema"](**request.tool_input)
        except ValidationError as e:
            logger.warning("tool_schema_validation_failed", tool=tool_name, error=str(e))
            return self._rejected_result(
                request,
                error=f"Schema validation failed: {e.error_count()} error(s). {str(e)}",
            )

        # Step 3 + 4: Risk routing
        if risk_level == "LOW":
            return self._execute_low_risk(
                tool_name=tool_name,
                validated_input=validated_input,
                original_input=request.tool_input,
                conversation_id=conversation_id,
                requested_by=request.requested_by,
            )
        else:
            return self._queue_high_risk(
                tool_name=tool_name,
                validated_input=validated_input,
                original_input=request.tool_input,
                conversation_id=conversation_id,
                requested_by=request.requested_by,
            )

    # --------------------------------------------------------
    # LOW RISK: Execute immediately
    # --------------------------------------------------------

    def _execute_low_risk(
        self,
        tool_name: str,
        validated_input: Any,
        original_input: dict,
        conversation_id: str,
        requested_by: str,
    ) -> ToolCallResult:

        executor_name = TOOL_REGISTRY[tool_name]["executor"]
        executor_fn = getattr(self, executor_name)

        start = time.time()
        try:
            output = executor_fn(validated_input)
            latency_ms = int((time.time() - start) * 1000)

            result = ToolCallResult(
                tool_name=tool_name,
                tool_input=original_input,
                tool_output=output,
                status="auto_executed",
                risk_level="LOW",
                latency_ms=latency_ms,
            )

            self._log_tool_call(result, conversation_id)
            logger.info("tool_auto_executed", tool=tool_name, latency_ms=latency_ms)
            return result

        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            logger.error("tool_execution_failed", tool=tool_name, error=str(e))
            return self._rejected_result(request=ToolCallRequest(
                tool_name=tool_name,
                tool_input=original_input,
                risk_level="LOW",
                requested_by=requested_by,
            ), error=str(e))

    # --------------------------------------------------------
    # HIGH RISK: Push to approval queue
    # --------------------------------------------------------

    def _queue_high_risk(
        self,
        tool_name: str,
        validated_input: Any,
        original_input: dict,
        conversation_id: str,
        requested_by: str,
    ) -> ToolCallResult:

        tool_call_id = str(uuid.uuid4())
        approval_id  = str(uuid.uuid4())

        # Step 1: Log tool call FIRST (approval queue references this ID)
        pending_result = ToolCallResult(
            tool_name=tool_name,
            tool_input=original_input,
            tool_output={"approval_id": approval_id, "status": "pending_approval"},
            status="pending_approval",
            risk_level="HIGH",
        )
        self._log_tool_call(pending_result, conversation_id, tool_call_id=tool_call_id)

        # Step 2: Build approval request
        approval_request = ApprovalRequest(
            approval_id=approval_id,
            tool_call_id=tool_call_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            tool_input=original_input,
            status="pending",
        )

        # Step 3: Push to Redis queue
        try:
            r = get_redis()
            r.lpush(
                APPROVAL_QUEUE_KEY,
                approval_request.model_dump_json(),
            )
            logger.info(
                "tool_queued_for_approval",
                tool=tool_name,
                approval_id=approval_id,
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.error("redis_queue_failed", tool=tool_name, error=str(e))

        # Step 4: Log to Supabase approval queue (tool_call_id now exists)
        self._log_approval_queue(approval_request, tool_call_id)

        return pending_result

    # --------------------------------------------------------
    # APPROVE: Execute a queued HIGH risk tool
    # --------------------------------------------------------

    def approve_and_execute(
        self,
        approval_id: str,
        reviewed_by: str = "human",
    ) -> ToolCallResult:
        """
        Called when a human approves a pending HIGH risk tool call.
        Fetches the approval record, executes the tool, updates Supabase.
        """
        supabase = get_supabase()

        # Fetch approval record
        try:
            resp = supabase.table("evals_approval_queue")\
                .select("*")\
                .eq("id", approval_id)\
                .single()\
                .execute()
            record = resp.data
        except Exception as e:
            raise ValueError(f"Approval record not found: {approval_id}. Error: {e}")

        if record["status"] != "pending":
            raise ValueError(f"Approval {approval_id} is already {record['status']}.")

        tool_name   = record["tool_name"]
        tool_input  = record["tool_input"]
        conversation_id = record["conversation_id"]

        config = TOOL_REGISTRY[tool_name]
        validated_input = config["schema"](**tool_input)
        executor_fn = getattr(self, config["executor"])

        start = time.time()
        output = executor_fn(validated_input)
        latency_ms = int((time.time() - start) * 1000)

        result = ToolCallResult(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=output,
            status="approved",
            risk_level="HIGH",
            latency_ms=latency_ms,
        )

        # Update approval queue record
        supabase.table("evals_approval_queue").update({
            "status":       "approved",
            "reviewed_by":  reviewed_by,
            "reviewed_at":  datetime.now(timezone.utc).isoformat(),
        }).eq("id", approval_id).execute()

        # Update tool call record
        supabase.table("evals_tool_calls").update({
            "status":       "approved",
            "approved_by":  reviewed_by,
            "tool_output":  output,
            "latency_ms":   latency_ms,
            "resolved_at":  datetime.now(timezone.utc).isoformat(),
        }).eq("id", record["tool_call_id"]).execute()

        logger.info("tool_approved_and_executed", tool=tool_name, approval_id=approval_id)
        return result

    # --------------------------------------------------------
    # REJECT: Reject a queued HIGH risk tool
    # --------------------------------------------------------

    def reject_tool_call(
        self,
        approval_id: str,
        rejection_reason: str,
        reviewed_by: str = "human",
    ) -> None:
        """
        Called when a human rejects a pending HIGH risk tool call.
        """
        supabase = get_supabase()

        supabase.table("evals_approval_queue").update({
            "status":           "rejected",
            "reviewed_by":      reviewed_by,
            "rejection_reason": rejection_reason,
            "reviewed_at":      datetime.now(timezone.utc).isoformat(),
        }).eq("id", approval_id).execute()

        logger.info("tool_rejected", approval_id=approval_id, reason=rejection_reason)

    # ============================================================
    # MOCK TOOL EXECUTORS
    # ============================================================

    def _execute_get_customer_profile(self, inp: GetCustomerProfileInput) -> dict:
        mock_profiles = {
            "cust_001": {
                "customer_id":  "cust_001",
                "name":         "Sarah Mitchell",
                "email":        "sarah@example.com",
                "plan":         "Pro",
                "status":       "active",
                "member_since": "2022-03-15",
                "balance_usd":  0.00,
            },
            "cust_002": {
                "customer_id":  "cust_002",
                "name":         "James Okafor",
                "email":        "james@example.com",
                "plan":         "Starter",
                "status":       "active",
                "member_since": "2023-07-01",
                "balance_usd":  -49.99,
            },
            "cust_003": {
                "customer_id":  "cust_003",
                "name":         "Priya Sharma",
                "email":        "priya@example.com",
                "plan":         "Enterprise",
                "status":       "suspended",
                "member_since": "2021-01-10",
                "balance_usd":  0.00,
            },
        }
        return mock_profiles.get(
            inp.customer_id,
            {"error": f"Customer {inp.customer_id} not found"},
        )

    def _execute_get_invoice_history(self, inp: GetInvoiceHistoryInput) -> dict:
        mock_invoices = {
            "cust_001": [
                {"invoice_id": "inv_001", "date": "2024-11-01", "amount": 99.00,  "status": "paid"},
                {"invoice_id": "inv_002", "date": "2024-12-01", "amount": 99.00,  "status": "paid"},
                {"invoice_id": "inv_003", "date": "2025-01-01", "amount": 99.00,  "status": "paid"},
                {"invoice_id": "inv_004", "date": "2025-01-01", "amount": 99.00,  "status": "duplicate"},
            ],
            "cust_002": [
                {"invoice_id": "inv_005", "date": "2024-12-01", "amount": 29.00,  "status": "paid"},
                {"invoice_id": "inv_006", "date": "2025-01-01", "amount": 29.00,  "status": "overdue"},
            ],
            "cust_003": [
                {"invoice_id": "inv_007", "date": "2024-10-01", "amount": 499.00, "status": "paid"},
                {"invoice_id": "inv_008", "date": "2024-11-01", "amount": 499.00, "status": "unpaid"},
            ],
        }
        invoices = mock_invoices.get(inp.customer_id, [])
        return {"customer_id": inp.customer_id, "invoices": invoices[:inp.limit]}

    def _execute_check_refund_policy(self, inp: CheckRefundPolicyInput) -> dict:
        return {
            "scenario": inp.scenario,
            "policy":   "Refunds are available within 30 days of charge for duplicate or erroneous billing. "
                        "Subscription refunds are prorated. Refund processing takes 5-7 business days. "
                        "Refunds are not available for usage-based charges already consumed.",
            "source":   "refund_policy_v2.pdf",
            "eligible": True,
        }

    def _execute_create_refund_ticket(self, inp: CreateRefundTicketInput) -> dict:
        ticket_id = f"refund_{str(uuid.uuid4())[:8].upper()}"
        return {
            "ticket_id":    ticket_id,
            "customer_id":  inp.customer_id,
            "amount":       inp.amount,
            "reason":       inp.reason,
            "status":       "created",
            "eta_days":     "5-7 business days",
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }

    def _execute_escalate_to_human(self, inp: EscalateToHumanInput) -> dict:
        ticket_id = f"esc_{str(uuid.uuid4())[:8].upper()}"
        return {
            "ticket_id":    ticket_id,
            "customer_id":  inp.customer_id,
            "reason":       inp.reason,
            "priority":     inp.priority,
            "status":       "escalated",
            "assigned_to":  "support_team_queue",
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }

    # ============================================================
    # SUPABASE LOGGING HELPERS
    # ============================================================

    def _log_tool_call(
        self,
        result: ToolCallResult,
        conversation_id: str,
        tool_call_id: Optional[str] = None,
    ) -> None:
        try:
            supabase = get_supabase()
            supabase.table("evals_tool_calls").insert({
                "id":               tool_call_id or str(uuid.uuid4()),
                "conversation_id":  conversation_id,
                "tool_name":        result.tool_name,
                "tool_input":       result.tool_input,
                "tool_output":      result.tool_output,
                "risk_level":       result.risk_level,
                "status":           result.status,
                "latency_ms":       result.latency_ms,
                "created_at":       datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.error("tool_call_log_failed", error=str(e))

    def _log_approval_queue(
        self,
        approval: ApprovalRequest,
        tool_call_id: str,
    ) -> None:
        try:
            supabase = get_supabase()
            supabase.table("evals_approval_queue").insert({
                "id":               approval.approval_id,
                "tool_call_id":     tool_call_id,
                "conversation_id":  approval.conversation_id,
                "tool_name":        approval.tool_name,
                "tool_input":       approval.tool_input,
                "status":           "pending",
                "created_at":       datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            logger.error("approval_queue_log_failed", error=str(e))

    def _rejected_result(
        self,
        request: ToolCallRequest,
        error: str,
    ) -> ToolCallResult:
        return ToolCallResult(
            tool_name=request.tool_name,
            tool_input=request.tool_input,
            tool_output={"error": error},
            status="rejected",
            risk_level=request.risk_level,
            error=error,
        )


# ============================================================
# SINGLETON INSTANCE
# ============================================================

gateway = ToolGateway()