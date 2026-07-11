# GRT Agent Chain — System Architecture Design

**Spec Reference:** `grt_agent_chain_spec.json` v1.0.0
**Author:** Swapna Ketavarapu
**Date:** 2026-04-22
**Status:** Draft

---

## 1. Execution Model

### 1.1 DAG (Not a Linear Chain)

The agents form a Directed Acyclic Graph with parallel execution where dependencies allow:

```
Phase 1 (DEFINE) — Sequential, strict ordering:
  Agent 0 (Incentive Auditor) → pre-scan
  Agent 1 (Domain Analyst)
    → Agent 2 (Goal Architect)
      → Agent 3 (Rule Derivation)
        → Agent 4 (Threshold Calibrator)
          → Agent 5 (Residue & HCI)
            → Agent 6 (Validator) ←── rework loops back to 2,3,4
              → Agent 17 (Truth Conflict Resolver) — if conflicts detected
                → Agent 7 (Finalizer)

Phase 2 (BUILD) — Parallel where independent:
  Agent 8 (UX Architect) ──────┐
  Agent 9 (Connector Identifier) ──┼──→ Agent 10 (Connecting Agent)
                                    │
  (Agent 8 and 9 run in parallel)

Phase 3 (TEST) — Sequential:
  Agent 11 (Test Case Author) → Agent 12 (Testing Agent)

Phase 4 (DEPLOY) — Gate:
  Agent 13 (Deployment Gate) — runs 7-layer validation

Phase 5 (EVOLVE) — Continuous:
  Agent 14 (Performance Monitor) — always running
  Agent 18 (Reality Feedback) — always running post-deploy
  Agent 15 (Version Controller) — on-demand
  Agent 16 (Evolution Agent) — triggered by 14 or 18
```

### 1.2 Execution Modes

| Mode | Description | When |
|------|-------------|------|
| `full_run` | All phases, sequential with parallel where allowed | New GRD from scratch |
| `define_only` | Phase 1 only, produces GRD JSON | Governance design workshops |
| `rework` | Single agent re-execution with accumulated state | Validator/Testing triggers |
| `evolve` | Phase 5 only, produces version diff | Triggered by Monitor/Reality |
| `emergency_halt` | Immediate stop, no new outputs | Circuit breaker triggered |

---

## 2. State Model

### 2.1 Chain State Store

Every chain run has a single source of truth:

```json
{
  "run_id": "uuid-v4",
  "created_at": "ISO8601",
  "status": "running | completed | halted | rework",
  "current_phase": "define | build | test | deploy | evolve",
  "current_agent_id": 3,
  "problem_statement": "original input text",
  "truth_layer_classification": { "primary": 4, "secondary": [5, 6] },
  "weight_snapshot": { "frozen at run start — weights don't change mid-run" },
  "agent_outputs": {
    "1": { "status": "completed", "output": {...}, "timestamp": "...", "confidence": 0.85 },
    "2": { "status": "completed", "output": {...}, "timestamp": "...", "confidence": 0.90 },
    "3": { "status": "in_progress", "output": null }
  },
  "rework_history": [
    { "from_agent": 6, "to_agent": 3, "reason": "...", "iteration": 1, "resolved": true }
  ],
  "threshold_fires": [
    { "agent_id": 3, "threshold": "T2", "detail": ">7 rules", "timestamp": "..." }
  ],
  "escalations": [],
  "cost_accumulator": {
    "llm_tokens": 45000,
    "human_review_minutes": 0,
    "calendar_seconds": 342,
    "rework_count": 1
  }
}
```

### 2.2 Persistence

| Component | Storage | Retention |
|-----------|---------|-----------|
| Active run state | In-memory + journaled to disk | Until run completes |
| Completed run outputs | Database (SQLite for single-node, Postgres for multi) | 7 years (Civilizational rule) |
| Learning logs | Append-only file per agent | 90 days hot, then archived |
| Weight history | Versioned config store | Indefinite |
| Frozen versions | Immutable artifact store (git or S3) | Indefinite |

### 2.3 Transactions

State transitions are atomic:
- Agent starts → status changes from `pending` to `in_progress` (single write)
- Agent completes → output written + status changes to `completed` (single transaction)
- Rework triggered → new entry in rework_history + target agent status reset to `pending` (single transaction)
- If crash occurs mid-agent: on recovery, replay from last checkpoint (the last completed agent)

---

## 3. Agent Interface Contracts

### 3.1 Universal Agent Interface

Every agent implements:

```python
class AgentInterface:
    def execute(self, input: AgentInput) -> AgentOutput:
        """Run the agent's logic. May call LLM, run computations, or orchestrate sub-tasks."""
        ...

    def validate_input(self, input: AgentInput) -> list[str]:
        """Return list of validation errors. Empty = valid."""
        ...

    def estimate_cost(self, input: AgentInput) -> CostEstimate:
        """Estimate tokens/time before execution."""
        ...

@dataclass
class AgentInput:
    run_id: str
    agent_id: int
    accumulated_state: dict          # outputs from all prior agents
    weight_snapshot: dict            # frozen weights for this run
    rework_context: ReworkContext | None  # if this is a rework invocation

@dataclass
class AgentOutput:
    agent_id: int
    status: Literal["completed", "rework_needed", "escalation_needed", "blocked"]
    output: dict                     # agent-specific structured output
    confidence: float                # 0.0 to 1.0 self-assessment
    threshold_fires: list[ThresholdFire]
    rework_request: ReworkRequest | None
    cost: CostRecord
    trace: TraceSpan

@dataclass
class ThresholdFire:
    threshold_id: str
    condition: str
    action: str
    truth_layer_affected: int | None

@dataclass
class ReworkRequest:
    target_agent_id: int
    failure_description: str
    required_change: str
    evidence: str

@dataclass
class TraceSpan:
    run_id: str
    span_id: str
    parent_span_id: str | None
    agent_id: int
    rework_depth: int
    start_time: str
    end_time: str
    weight_snapshot_hash: str
    truth_layer_context: int | None
```

### 3.2 Per-Agent I/O Schemas

#### Agent 1: Domain Analyst

```
Input:
  problem_statement: string
  domain_hints: string[] (optional)

Output:
  decision_space: string
  stakeholders: [{ name, role, cost_bearing, identifiable }]
  data_landscape: { available_sources, missing_data, data_quality_concerns }
  domain_risks: [{ risk, severity, truth_layer }]
  truth_layer_classification: { primary: int, secondary: int[], confidence: float }
  regulatory_context: string | null
```

#### Agent 2: Goal Architect

```
Input:
  domain_brief: Agent1Output
  accumulated_state.agent_1: {...}

Output:
  goal_statement: string
  criteria_scores: {
    frame_origin: { score: 0-2, detail: string },
    residue_declaration: { score: 0-2, detail: string },
    incentive_mapping: { score: 0-2, detail: string },
    non_goals: { score: 0-2, detail: string },
    temporal_condition: { score: 0-2, detail: string },
    composability: { score: 0-2, detail: string }
  }
  total_score: int (0-12)
  frame_owner: string
  temporal_expiry: string (ISO8601 or condition)
  residue_domains: [{ domain, weight, maps_to_reason }]
  non_goals: [string]
```

#### Agent 3: Rule Derivation

```
Input:
  goal: Agent2Output
  domain_brief: Agent1Output
  rework_context: { validator_finding, required_change } | null

Output:
  rules: [{
    id: string,
    name: string,
    type: "epistemic_territory | corruption_surface | irreversibility | vintage_declaration | incentive_transparency",
    description: string,
    enforcement: "schema_level | api_level | policy_only",
    testable: boolean,
    proxy_features: [string] | null
  }]
  rule_count: int
  enforcement_coverage: float (% with schema/api enforcement)
```

#### Agent 6: Validator / Adversary

```
Input:
  full_grd_draft: { goal, rules, thresholds, residue, hci, deployment_level }
  domain_brief: Agent1Output

Output:
  findings: [{
    severity: "critical | major | minor",
    category: "rule_gap | threshold_contradiction | proxy_unblocked | goal_incoherence | roster_incomplete",
    description: string,
    affected_truth_layer: int,
    recommended_action: string,
    rework_target_agent: int | null
  }]
  adversarial_scenarios_tested: int (must be ≥3)
  pass: boolean
  critical_count: int
```

#### Agent 13: Deployment Gate

```
Input:
  full_grd: FinalizedGRD
  test_results: Agent12Output
  build_artifacts: { ux_traceability, connector_health, integration_tests }
  cost_accumulator: CostRecord
  hci_computed: HCIResult

Output:
  decision: "deploy | block"
  seven_layer_validation: [{
    layer: int,
    name: string,
    status: "pass | fail | flag",
    finding: string | null
  }]
  block_reasons: [string] | null
  deployment_level: int
  deployment_rationale: string
```

---

## 4. Operational Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| LLM API unavailable | HTTP timeout or 5xx | Retry with exponential backoff (1s, 4s, 16s). After 3 retries → mark agent as `infra_blocked`, notify deployment_owner |
| LLM returns empty/malformed output | Output validation fails | Retry once with explicit "produce structured output" instruction. If still empty → mark `output_invalid`, trigger rework to self with stricter prompt |
| Agent exceeds token budget | Token counter exceeds 2x estimate | Truncate input (summarize prior agent outputs), retry. If still over → flag for prompt optimization |
| Concurrent rework collision | Two rework requests target same agent simultaneously | Queue second rework. Max one active rework per target agent. FIFO ordering. |
| State store crash | Write fails or data corruption detected | Replay from last checkpoint (last completed agent). Journal ensures no lost writes. |
| Weight dashboard crash mid-change | Browser crash or network drop | All weight changes are two-phase: (1) write to journal, (2) commit. On recovery, uncommitted changes are shown for user re-confirmation. |
| Learning log unbounded growth | Storage monitoring exceeds threshold | Archive logs >90 days to cold storage. Keep summary statistics hot. Full logs recoverable within 24 hours. |
| Circuit breaker triggered during active rework | Emergency halt fires while agent is mid-execution | Immediately abort agent execution. Mark run as `emergency_halted`. Preserve all accumulated state for post-mortem. |

---

## 5. Distributed Tracing

### 5.1 Trace Structure

Every agent invocation carries context:

```json
{
  "trace_id": "run-uuid (same for entire chain run)",
  "span_id": "invocation-uuid (this specific agent call)",
  "parent_span_id": "uuid of the agent that triggered this one (or null for Agent 1)",
  "agent_id": 3,
  "agent_name": "Rule Derivation",
  "rework_depth": 0,
  "invocation_type": "initial | rework | parallel",
  "weight_snapshot_hash": "sha256 of weight config at invocation time",
  "truth_layer_context": 4,
  "timing": {
    "queued_at": "ISO8601",
    "started_at": "ISO8601",
    "completed_at": "ISO8601",
    "llm_latency_ms": 2340,
    "total_duration_ms": 2580
  },
  "cost": {
    "input_tokens": 3200,
    "output_tokens": 890,
    "total_tokens": 4090
  },
  "outcome": "completed | rework_triggered | escalated | blocked | failed"
}
```

### 5.2 Trace Queries

The tracing system must answer:
- "Why did deployment fail?" → Walk backwards from Agent 13 block reason through the spans
- "What caused this rework?" → Follow parent_span_id chain to find originating failure
- "Which agent is the bottleneck?" → Aggregate timing.total_duration_ms by agent_id
- "Did weight changes affect this run?" → Compare weight_snapshot_hash across runs
- "How many tokens did this GRD cost?" → Sum cost.total_tokens across all spans in trace_id

---

## 6. Concurrency & Parallelism

### 6.1 Parallel Execution Rules

| Agents | Can run in parallel? | Reason |
|--------|---------------------|--------|
| 8, 9 | Yes | UX and Connectors are independent given the same GRD |
| 11, (waiting for 10) | Partial — 11 can start spec-level tests while 10 builds | Test cases derived from GRD, not from implementation |
| 14, 18 | Yes | Monitor and Reality Feedback are independent continuous processes |
| 15, 16 | No | Version Controller gates Evolution Agent output |
| Any Phase 1 agents | No | Strict sequential dependency |

### 6.2 Execution Scheduler

```python
class ChainScheduler:
    def get_ready_agents(self, state: ChainState) -> list[int]:
        """Return agent IDs whose dependencies are satisfied and are not blocked."""
        ...

    def can_run_parallel(self, agent_a: int, agent_b: int) -> bool:
        """Check if two agents can execute simultaneously."""
        ...

    def schedule_next(self, state: ChainState) -> list[AgentInvocation]:
        """Return the next batch of agent invocations to dispatch."""
        ...
```

### 6.3 Concurrency Limits

- Max 3 agents running simultaneously (LLM API rate limits)
- Max 1 rework active per target agent
- Max 1 weight change transaction in flight at a time
- Monitor and Reality Feedback run on separate scheduling loop (not counted toward agent limit)

---

## 7. Multi-GRD Awareness (v2.0 Hook)

Not implemented in v1, but the architecture leaves room:

### 7.1 GRD Registry

```json
{
  "registry_id": "org-level",
  "grds": [
    { "grd_id": "GRT-G-002", "domain": "procurement", "version": "1.0", "owner": "Swapna", "status": "active" },
    { "grd_id": "GRT-G-003", "domain": "supply_chain", "version": "0.9", "owner": "TBD", "status": "draft" }
  ],
  "declared_couplings": [
    { "grd_a": "GRT-G-002", "grd_b": "GRT-G-003", "coupling_type": "shared_supplier_base", "conflict_potential": "medium" }
  ]
}
```

### 7.2 Cross-GRD Conflict Detection

Agent 17 (Truth Conflict Resolver) extended in v2 to:
- Detect when one GRD's goal contradicts another GRD's non-goal
- Detect when two GRDs claim authority over the same data domain
- Surface shared proxy features that one GRD blocks and another doesn't

---

## 8. Technology Stack (Recommended)

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Agent runtime | Python 3.11+ | Matches existing grt_engine |
| LLM calls | litellm (multi-provider abstraction) | Supports Claude, GPT, Grok, local models |
| State store | SQLite (single-node) / Postgres (multi) | Transactional, journaled, queryable |
| Scheduler | Custom DAG scheduler (no external dependency) | Simple enough to not need Airflow/Celery |
| Tracing | JSON log files → queryable with jq | No infra dependency. Upgrade to OpenTelemetry in v2 if scale warrants |
| Authority Dashboard | React + Supabase auth (or self-contained HTML for MVP) | Role-based access, real-time weight updates |
| Version store | Git (frozen versions as tagged commits) | Immutable, auditable, 7-year retention built in |
| Cost tracking | In-process accumulator, written to state store | No external billing integration needed for v1 |

### 8.1 MVP vs Full

| | MVP (single user, local) | Full (team, deployed) |
|---|---|---|
| State | SQLite file | Postgres |
| Dashboard | Self-contained HTML (like existing) | React + auth |
| Tracing | JSON logs | OpenTelemetry |
| Scheduler | Sequential (no parallelism) | DAG with 3-agent concurrency |
| Multi-GRD | Not supported | Registry + cross-GRD conflict |
| Auth | None (single user) | Role-based (6 roles) |

---

## 9. Deployment Architecture

### 9.1 Single-Node (MVP)

```
┌─────────────────────────────────────┐
│  Local Machine                       │
│                                      │
│  ┌──────────┐    ┌──────────────┐   │
│  │ CLI      │───→│ Chain Engine  │   │
│  │ or HTML  │    │ (scheduler + │   │
│  │ Dashboard│←───│  agents)     │   │
│  └──────────┘    └──────┬───────┘   │
│                         │            │
│              ┌──────────┴─────┐      │
│              │  SQLite        │      │
│              │  (state + logs)│      │
│              └────────────────┘      │
│                         │            │
│              ┌──────────┴─────┐      │
│              │  LLM APIs      │      │
│              │  (Claude/GPT)  │      │
│              └────────────────┘      │
└─────────────────────────────────────┘
```

### 9.2 Team Deployment (v2)

```
┌──────────────┐     ┌──────────────────────────┐
│ Dashboard    │────→│  API Server              │
│ (React +    │     │  (FastAPI)               │
│  Auth)      │←────│                          │
└──────────────┘     │  ┌──────────────────┐   │
                     │  │ Chain Engine      │   │
┌──────────────┐     │  │ (DAG scheduler)  │   │
│ CLI          │────→│  └────────┬─────────┘   │
└──────────────┘     │           │             │
                     │  ┌────────┴─────────┐   │
                     │  │ Postgres         │   │
                     │  │ (state + history)│   │
                     │  └──────────────────┘   │
                     │           │             │
                     │  ┌────────┴─────────┐   │
                     │  │ LLM Gateway      │   │
                     │  │ (litellm proxy)  │   │
                     │  └──────────────────┘   │
                     └──────────────────────────┘
```

---

## 10. Open Design Decisions

| Decision | Options | Leaning | Depends on |
|----------|---------|---------|------------|
| Agent prompt format | System prompt vs few-shot vs tool-use | System prompt + structured output | Which LLM providers support tool-use |
| Rework state reset | Full reset to target agent vs incremental patch | Incremental (pass rework_context with specific change request) | Whether agents can handle partial updates |
| Dashboard technology | Self-contained HTML vs React app | HTML for MVP, React for team deployment | Number of concurrent users |
| Weight change propagation | Immediate (next invocation) vs batched (next run) | Next run (spec says "never mid-execution") | Already decided in spec |
| Learning log format | Structured JSON vs natural language | Structured JSON with a `lesson_summary` text field | Queryability needs |
| Emergency halt scope | Stop all runs or just the triggering run | All runs in the organization (the harm is real, not per-run) | Already decided in spec |
