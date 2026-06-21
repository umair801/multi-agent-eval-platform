# ============================================================
# AgAI_31: Pydantic Models + LangGraph State
# ============================================================

from typing import Any, Optional
from typing_extensions import TypedDict, Annotated
from pydantic import BaseModel, Field
from datetime import datetime
import operator
import uuid


# ============================================================
# 1. LANGGRAPH STATE
# Passed between all 6 agents through the graph
# ============================================================

class AgentState(TypedDict, total=False):

    # --- Conversation identifiers ---
    session_id:             str
    conversation_id:        str
    turn_id:                int

    # --- User input ---
    user_message:           str

    # --- Router Agent output ---
    intent:                 str         # billing_query | refund_request | policy_check | escalation | general

    # --- Billing Agent output ---
    customer_profile:       Optional[dict]
    invoice_history:        Optional[list]
    billing_context:        Optional[str]

    # --- Policy/Grounding Agent output ---
    policy_excerpts:        Optional[list]  # list of {text, source, score}
    grounding_sources:      Optional[list]  # source citations used

    # --- Tool Gateway output ---
    tool_calls_requested:   Optional[list]  # tools the agent wants to call
    tool_calls_approved:    Optional[list]  # tools approved by gateway
    tool_calls_rejected:    Optional[list]  # tools rejected by gateway
    pending_approval_ids:   Optional[list]  # approval queue IDs waiting on human

    # --- Tool Executor Agent output ---
    tool_results:           Optional[list]  # {tool_name, input, output, latency_ms, status}

    # --- Response Agent output ---
    final_response:         Optional[str]
    citations:              Optional[list]

    # --- Eval/Safety Agent output ---
    eval_scores:            Optional[dict]  # {task_success, grounding_accuracy, ...}
    flagged_for_review:     Optional[bool]
    failure_category:       Optional[str]

    # --- Observability ---
    trace_steps:            Annotated[list, operator.add]  # append-only trace log
    errors:                 Annotated[list, operator.add]  # append-only error log

    # --- Metadata ---
    primary_model:          str
    fallback_model:         str
    total_tokens_in:        int
    total_tokens_out:       int
    total_cost_usd:         float
    total_latency_ms:       int


# ============================================================
# 2. TOOL GATEWAY MODELS
# ============================================================

class ToolCallRequest(BaseModel):
    tool_name:      str
    tool_input:     dict
    risk_level:     str = Field(default="LOW", pattern="^(LOW|HIGH)$")
    requested_by:   str  # agent name


class ToolCallResult(BaseModel):
    tool_name:      str
    tool_input:     dict
    tool_output:    Optional[Any] = None
    status:         str  # auto_executed | pending_approval | approved | rejected
    risk_level:     str
    latency_ms:     Optional[int] = None
    error:          Optional[str] = None


class ApprovalRequest(BaseModel):
    approval_id:    str
    tool_call_id:   str
    conversation_id: str
    tool_name:      str
    tool_input:     dict
    status:         str = "pending"
    created_at:     datetime = Field(default_factory=datetime.utcnow)


class ApprovalDecision(BaseModel):
    approval_id:        str
    action:             str = Field(pattern="^(approve|reject)$")
    reviewed_by:        str = "human"
    rejection_reason:   Optional[str] = None


# ============================================================
# 3. MOCK TOOL INPUT SCHEMAS
# Schema validation enforced by the Tool Gateway
# ============================================================

class GetCustomerProfileInput(BaseModel):
    customer_id:    str = Field(min_length=1, max_length=50)


class GetInvoiceHistoryInput(BaseModel):
    customer_id:    str = Field(min_length=1, max_length=50)
    limit:          int = Field(default=10, ge=1, le=100)


class CheckRefundPolicyInput(BaseModel):
    scenario:       str = Field(min_length=5, max_length=500)


class CreateRefundTicketInput(BaseModel):
    customer_id:    str = Field(min_length=1, max_length=50)
    amount:         float = Field(gt=0, le=10000)
    reason:         str = Field(min_length=10, max_length=500)


class EscalateToHumanInput(BaseModel):
    customer_id:    str = Field(min_length=1, max_length=50)
    reason:         str = Field(min_length=10, max_length=500)
    priority:       str = Field(pattern="^(low|medium|high|critical)$")


# ============================================================
# 4. TRACE STEP MODEL
# Written to evals_trace_steps for every agent step
# ============================================================

class TraceStep(BaseModel):
    model_config = {"protected_namespaces": ()}
    conversation_id:    str
    turn_id:            int
    agent_name:         str
    step_type:          str     # prompt_sent | model_response | tool_call | tool_result | routing_decision
    prompt_text:        Optional[str] = None
    model_response:     Optional[str] = None
    tool_name:          Optional[str] = None
    tool_input:         Optional[dict] = None
    tool_output:        Optional[Any] = None
    latency_ms:         Optional[int] = None
    token_count_input:  Optional[int] = None
    token_count_output: Optional[int] = None
    cost_usd:           Optional[float] = None
    error:              Optional[str] = None
    timestamp:          datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# 5. EVAL MODELS
# ============================================================

class EvalScores(BaseModel):
    task_success:           float = Field(ge=0.0, le=1.0)
    grounding_accuracy:     float = Field(ge=0.0, le=1.0)
    tool_correctness:       float = Field(ge=0.0, le=1.0)
    policy_compliance:      float = Field(ge=0.0, le=1.0)
    escalation_correctness: float = Field(ge=0.0, le=1.0)
    avg_latency_ms:         Optional[int] = None
    total_cost_usd:         Optional[float] = None
    flagged_for_review:     bool = False
    failure_category:       Optional[str] = None
    eval_notes:             Optional[str] = None


class EvalTestCase(BaseModel):
    case_id:                    str
    input_message:              str
    expected_intent:            str
    expected_tool_calls:        list[str]
    expected_grounding_sources: list[str]
    expected_escalation:        bool
    category:                   str     # billing_query | duplicate_charge | refund_policy | escalation | out_of_scope


class EvalRunReport(BaseModel):
    run_id:                     str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt_version_id:          Optional[str] = None
    model:                      Optional[str] = None
    total_cases:                int
    passed:                     int
    failed:                     int
    task_success_rate:          float
    grounding_accuracy_avg:     float
    tool_correctness_avg:       float
    policy_compliance_avg:      float
    escalation_accuracy_avg:    float
    avg_latency_ms:             int
    total_cost_usd:             float
    results:                    list[dict]
    created_at:                 datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# 6. API REQUEST / RESPONSE MODELS
# ============================================================

class ChatRequest(BaseModel):
    message:        str = Field(min_length=1, max_length=2000)
    session_id:     Optional[str] = None
    customer_id:    Optional[str] = None


class ChatResponse(BaseModel):
    session_id:     str
    response:       str
    intent:         Optional[str] = None
    citations:      Optional[list] = None
    eval_scores:    Optional[dict] = None
    flagged:        Optional[bool] = None
    pending_approvals: Optional[list] = None


class MetricsResponse(BaseModel):
    avg_latency_ms:         float
    avg_cost_per_turn_usd:  float
    task_success_rate:      float
    tool_approval_rate:     float
    escalation_rate:        float
    total_conversations:    int
    total_tool_calls:       int
    flagged_conversations:  int