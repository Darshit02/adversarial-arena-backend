"""LangGraph state graph orchestrator for adversarial robustness benchmark runs."""

import time
from typing import Any
from langgraph.graph import END, START, StateGraph
from redis.asyncio import Redis

from app.config import get_settings
from app.core.logging import get_logger
from app.engine.evaluator import (
    aggregate_by_category,
    compute_rfr,
    confidence_interval,
)
from app.engine.state import RunConfig, RunMetrics, RunState
from app.probes.base import BaseProbe, ProbeAttempt, ProbeResult
from app.probes.registry import get_probe_class
from app.targets.base import TargetModel
from app.targets.mock_client import MockTargetModel
from app.validators.base import BaseValidator
from app.validators.registry import get_validator_class

logger = get_logger(__name__)


class OrchestrationContext:
    """Holds active probe instances, validator instances, and ModelUnderTest during graph execution."""

    def __init__(
        self,
        config: RunConfig,
        mut: TargetModel | None = None,
        validators: list[BaseValidator] | None = None,
        redis: Redis | None = None,
    ) -> None:
        self.config = config
        self.mut = mut or MockTargetModel()
        self.validators = validators or []
        self.redis = redis
        self.probes: list[BaseProbe] = []
        self.attempts: list[ProbeAttempt] = []
        self.current_attempt: ProbeAttempt | None = None
        self.current_verdict: dict[str, Any] = {"allowed": True, "reason": "Passed", "confidence": 1.0}
        self.current_response: str = ""
        self.current_latency: float = 0.0
        self.current_tokens: int = 0
        self.is_blocked: bool = False


# Active execution contexts indexed by run_id
_ACTIVE_CONTEXTS: dict[str, OrchestrationContext] = {}


async def _check_abort_signal(run_id: str, redis: Redis | None) -> bool:
    """Check whether an abort key has been set in Redis."""
    if redis is None:
        return False
    try:
        exists = await redis.exists(f"run:{run_id}:abort")
        return bool(exists)
    except Exception as e:
        logger.warning("Error checking Redis abort key", run_id=run_id, error=str(e))
        return False


# ------------------------------------------------------------------------------
# LangGraph Node Handlers
# ------------------------------------------------------------------------------

async def setup_node(state: RunState) -> dict[str, Any]:
    """Initialize orchestration context, instantiate probes and validators."""
    run_id = state["run_id"]
    config = state["config"]
    ctx = _ACTIVE_CONTEXTS.get(run_id) or OrchestrationContext(config)
    _ACTIVE_CONTEXTS[run_id] = ctx

    # Instantiate validators from config if not provided
    if not ctx.validators and config.validator_configs:
        for v_conf in config.validator_configs:
            v_type = v_conf.get("type", "keyword_filter")
            v_cls = get_validator_class(v_type)
            ctx.validators.append(v_cls(v_conf.get("params", {})))

    # Instantiate probes
    ctx.probes = []
    for p_type in config.probe_types:
        p_cls = get_probe_class(p_type)
        p_params = config.probe_params.get(p_type, {})
        ctx.probes.append(p_cls(params=p_params, mut=ctx.mut))

    # Pre-generate attempts for the first probe
    if ctx.probes:
        ctx.attempts = await ctx.probes[0].generate(
            seed_prompts=config.seed_prompts,
            risk_category=config.risk_category,
        )

    return {
        "status": "running",
        "current_probe_idx": 0,
        "current_attempt_idx": 0,
        "results": [],
        "errors": [],
    }


async def probe_mutate_node(state: RunState) -> dict[str, Any]:
    """Retrieve current attempt or mutate probe prompt."""
    run_id = state["run_id"]
    ctx = _ACTIVE_CONTEXTS.get(run_id)

    # Check abort condition
    if await _check_abort_signal(run_id, ctx.redis if ctx else None):
        return {"status": "aborted"}

    if not ctx or not ctx.attempts:
        return {"status": "completed"}

    attempt_idx = state.get("current_attempt_idx", 0)
    if attempt_idx < len(ctx.attempts):
        ctx.current_attempt = ctx.attempts[attempt_idx]
    else:
        ctx.current_attempt = None

    return {"status": "running"}


async def validator_chain_node(state: RunState) -> dict[str, Any]:
    """Execute safety validators in sequential order."""
    run_id = state["run_id"]
    ctx = _ACTIVE_CONTEXTS.get(run_id)
    if not ctx or not ctx.current_attempt:
        return {}

    prompt = ctx.current_attempt.cumulative_prompt
    ctx.is_blocked = False
    ctx.current_verdict = {"allowed": True, "reason": "Passed all validators", "confidence": 1.0}

    for validator in ctx.validators:
        verdict = await validator.check(prompt, context={"risk_category": state["config"].risk_category})
        if not verdict.allowed:
            ctx.is_blocked = True
            ctx.current_verdict = verdict.to_dict()
            ctx.current_response = f"[BLOCKED BY VALIDATOR: {verdict.validator_name}] {verdict.reason}"
            ctx.current_latency = 5.0
            ctx.current_tokens = 0
            break

    return {}


async def mut_query_node(state: RunState) -> dict[str, Any]:
    """Query ModelUnderTest if prompt passed all validators."""
    run_id = state["run_id"]
    ctx = _ACTIVE_CONTEXTS.get(run_id)
    if not ctx or not ctx.current_attempt:
        return {}

    if ctx.is_blocked:
        return {}

    start_time = time.perf_counter()
    try:
        gen = await ctx.mut.generate(ctx.current_attempt.cumulative_prompt)
        ctx.current_response = gen.text
        ctx.current_latency = gen.latency_ms or ((time.perf_counter() - start_time) * 1000)
        ctx.current_tokens = gen.tokens_used
    except Exception as e:
        ctx.current_response = f"[MUT ERROR]: {e}"
        ctx.current_latency = (time.perf_counter() - start_time) * 1000
        ctx.current_tokens = 0
        state.get("errors", []).append(str(e))

    return {}


async def evaluation_node(state: RunState) -> dict[str, Any]:
    """Score the response and construct a ProbeResult."""
    run_id = state["run_id"]
    ctx = _ACTIVE_CONTEXTS.get(run_id)
    if not ctx or not ctx.current_attempt:
        return {}

    prompt = ctx.current_attempt.cumulative_prompt
    response = ctx.current_response
    attempt_idx = state.get("current_attempt_idx", 0)
    current_probe = ctx.probes[state.get("current_probe_idx", 0)]

    if ctx.is_blocked:
        is_fail = False
        score = 0.0
        reason = ctx.current_verdict.get("reason", "Blocked by safety validator")
    else:
        is_fail, score, reason = current_probe.evaluate_response(prompt, response)

    result = ProbeResult(
        attempt_index=attempt_idx,
        probe_type=current_probe.name,
        seed_prompt=ctx.current_attempt.seed_prompt,
        prompt=prompt,
        response=response,
        validator_verdict=ctx.current_verdict,
        is_failure=is_fail,
        score=score,
        evaluation_reason=reason,
        latency_ms=ctx.current_latency,
        tokens_used=ctx.current_tokens,
        turn_history=[{"category": state["config"].risk_category, "score": score}],
    )

    next_attempt_idx = attempt_idx + 1
    return {
        "results": [result],
        "current_attempt_idx": next_attempt_idx,
    }


async def finalize_node(state: RunState) -> dict[str, Any]:
    """Aggregate run metrics, confidence intervals, and mark completion."""
    run_id = state["run_id"]
    results = state.get("results", [])
    total = len(results)
    failures = sum(1 for r in results if r.is_failure)
    blocks = sum(1 for r in results if not r.validator_verdict.get("allowed", True))
    total_tokens = sum(r.tokens_used for r in results)
    avg_latency = (sum(r.latency_ms for r in results) / total) if total > 0 else 0.0

    rfr = compute_rfr(results)
    ci = confidence_interval(failures, total)
    cat_rfr = aggregate_by_category(results)

    metrics = RunMetrics(
        rfr=rfr,
        total_attempts=total,
        failed_attempts=failures,
        validator_blocks=blocks,
        average_latency_ms=round(avg_latency, 2),
        total_tokens=total_tokens,
        category_rfr=cat_rfr,
        confidence_interval_95=ci,
    )

    # Clean up active memory context
    _ACTIVE_CONTEXTS.pop(run_id, None)

    final_status = "aborted" if state.get("status") == "aborted" else "completed"
    return {
        "metrics": metrics,
        "status": final_status,
    }


# ------------------------------------------------------------------------------
# Conditional Edge Router
# ------------------------------------------------------------------------------

def route_after_evaluation(state: RunState) -> str:
    """Decide whether to execute more attempts, transition to next probe, or finalize."""
    if state.get("status") == "aborted":
        return "finalize"

    run_id = state["run_id"]
    ctx = _ACTIVE_CONTEXTS.get(run_id)
    if not ctx:
        return "finalize"

    attempt_idx = state.get("current_attempt_idx", 0)
    if attempt_idx < len(ctx.attempts):
        return "probe_mutate"

    # Check if more probes remain
    probe_idx = state.get("current_probe_idx", 0) + 1
    if probe_idx < len(ctx.probes):
        state["current_probe_idx"] = probe_idx
        state["current_attempt_idx"] = 0
        return "probe_mutate"

    return "finalize"


# ------------------------------------------------------------------------------
# StateGraph Builder
# ------------------------------------------------------------------------------

def build_orchestrator_graph() -> Any:
    """Construct the compiled LangGraph StateGraph for benchmark runs."""
    builder = StateGraph(RunState)

    builder.add_node("setup", setup_node)
    builder.add_node("probe_mutate", probe_mutate_node)
    builder.add_node("validator_chain", validator_chain_node)
    builder.add_node("mut_query", mut_query_node)
    builder.add_node("evaluation", evaluation_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "setup")
    builder.add_edge("setup", "probe_mutate")
    builder.add_edge("probe_mutate", "validator_chain")
    builder.add_edge("validator_chain", "mut_query")
    builder.add_edge("mut_query", "evaluation")
    builder.add_conditional_edges(
        "evaluation",
        route_after_evaluation,
        {
            "probe_mutate": "probe_mutate",
            "finalize": "finalize",
        },
    )
    builder.add_edge("finalize", END)

    return builder.compile()


async def run_graph(
    run_id: str,
    config: RunConfig,
    mut: TargetModel | None = None,
    validators: list[BaseValidator] | None = None,
    redis: Redis | None = None,
) -> RunMetrics:
    """Execute orchestrator graph and return computed benchmark metrics."""
    _ACTIVE_CONTEXTS[run_id] = OrchestrationContext(
        config=config,
        mut=mut,
        validators=validators,
        redis=redis,
    )

    initial_state: RunState = {
        "run_id": run_id,
        "config": config,
        "seed_prompts": config.seed_prompts,
        "current_probe_idx": 0,
        "current_attempt_idx": 0,
        "results": [],
        "metrics": RunMetrics(),
        "errors": [],
        "status": "pending",
        "metadata": {},
    }

    graph = build_orchestrator_graph()
    final_state = await graph.ainvoke(initial_state)
    return final_state["metrics"]
