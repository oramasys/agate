# Agate ↔ MHS Cold-Local-Metal Convergence

**Status:** architecture direction / non-normative roadmap  
**Date:** 2026-08-29  
**Applies to:** `oramasys/agate`, OramaSys hardware-policy planning, and the Claude-Desktop-LLM local-model integration boundary

## 1. Position

Agate is the OramaSys hardware capability, affinity, and routing contract for **cold-local-metal compute**: operator-owned local CPU/GPU/accelerator resources used to host and run local language models.

Anthropic's Model Hardware Standard (MHS) is currently a research preview. Public materials describe a model-agnostic hardware abstraction in which devices expose machine-readable state, capabilities/procedures, physical characteristics, discoverability, and enforced safety limits through a standardized driver/interface layer.

Agate SHOULD converge with the subset of those ideas that apply cleanly to local compute hardware, but MUST NOT claim MHS conformance until Anthropic publishes a sufficiently stable, normative specification and conformance surface.

The convergence goal is therefore:

```text
MHS general physical-device model
  identity
  capability
  state
  procedure
  constraint
  measurement
  safety boundary
        |
        | profile / semantic convergence
        v
Agate cold-local-metal profile
  host + accelerator identity
  compute capability
  memory / VRAM state
  model fit + affinity
  approved placement constraints
  host / accelerator readiness
  load/unload eligibility
  local performance measurements
        |
        v
Claude-Desktop-LLM
  canonical local-model integration layer
        |
     +--+--+
     |     |
     v     v
  Ollama  LM Studio
```

Agate remains the **policy/capability authority**. Claude-Desktop-LLM remains the **runtime/provider adapter authority**.

## 2. What "cold-local-metal" means

For Agate, cold-local-metal means directly operator-controlled physical compute resources rather than an abstract cloud placement target.

Initial families include:

```text
Apple Silicon
  Metal / MLX
  unified memory

NVIDIA
  CUDA
  VRAM

AMD
  ROCm
  VRAM

CPU-only fallback
  system RAM
  local inference runtime
```

The phrase does not require that hardware literally be powered off or thermally cold. It distinguishes **local physical compute inventory and constraints** from generic remote/cloud execution policy.

## 3. Conceptual bundle with Claude-Desktop-LLM

The intended bundle is deliberately split by authority.

### Agate owns

- local host/accelerator capability descriptions;
- hardware-tier classification;
- model fit and affinity;
- placement verdicts such as `PREFER`, `ALLOW`, and `NEVER`;
- hard resource constraints that must be checked before model dispatch/load;
- host/accelerator readiness and hardware-state facts needed to decide placement;
- future standardized local-compute state/capability representation;
- future MHS compatibility/profile mapping if the public MHS standard stabilizes.

Agate does **not** own provider health, loaded-model state, provider lifecycle, or provider-specific
runtime availability. Those are runtime/provider-adapter facts. Agate may consume a narrow,
normalized readiness input from an adapter when a placement decision needs it, but that does not
transfer provider-state authority into Agate.

### Claude-Desktop-LLM owns

- the canonical local-model tool/server implementation;
- the provider contract and canonical tool registry;
- canonical Ollama provider integration;
- canonical LM Studio provider integration;
- MCP-facing local-model tools for Claude Desktop / Claude Code;
- local provider health, model enumeration, inference, chat, embeddings, and provider-specific model operations;
- provider/runtime configuration and request translation;
- provider-native observability integration against Ollama and LM Studio.

### OramaSys upper layers own

- task-level orchestration;
- model-selection policy above raw hardware fit;
- effect/approval policy;
- evaluation and promotion policy;
- workflow semantics.

### Perpetua / security layers own

- generic endpoint authorization and safe transport where required;
- redaction/privacy boundaries;
- operational evidence and security invariants;
- other cross-cutting runtime controls that are not hardware-affinity semantics.

No lower layer should depend back on an upper adapter to define its contract.

## 4. MHS semantic mapping for local compute

This table is a conceptual mapping only. It is not an assertion about final MHS field names or wire formats.

| MHS-style concept | Agate local-compute interpretation |
| --- | --- |
| Device identity | host and accelerator identity; runtime identity only as an external adapter reference |
| Capability | backend support: Metal/MLX, CUDA, ROCm, CPU; memory capacity; supported hardware features |
| State | available memory/VRAM, host/accelerator readiness, utilization, optional thermal/power readings |
| Procedure | inspect capability; determine fit; approve/refuse placement; optionally request runtime load/unload through an adapter |
| Measurement | hardware-side latency/throughput evidence, memory use, load-related resource cost, context capacity |
| Constraint | model-fit floor, memory budget, forbidden hardware tier, operator policy |
| Safety boundary | hard placement/resource limits that cannot be bypassed accidentally by orchestration |
| Discovery | local/fleet inventory of eligible compute devices and accelerator readiness |

Agate should model **hardware facts and policy**. Provider health, loaded-model state, and
provider-specific operations belong behind adapters such as Claude-Desktop-LLM rather than being
embedded directly into Agate's core schema.

## 5. Near-term schema policy

Agate v1 MUST remain stable while MHS is still a research preview.

Therefore, near-term work SHOULD focus on additive, implementation-independent concepts that are useful even without MHS:

1. distinguish physical host identity from abstract tier labels;
2. describe accelerator backend and memory capacity;
3. allow explicit resource requirements for a model;
4. define machine-readable capability/state snapshots separately from operator policy;
5. retain a single authoritative policy source;
6. keep runtime/provider details in adapters.

Do **not** add speculative fields merely because they seem likely to appear in MHS.

## 6. Future Agate profile shape

A future additive profile may conceptually separate facts from policy:

```text
ComputeDevice
  id
  host
  accelerator_kind
  backend
  total_memory
  available_memory
  capabilities
  state

ModelRequirement
  min_memory
  preferred_backend
  supported_backends
  context_requirement

PlacementPolicy
  device/model verdict
  hard constraints
  operator overrides

PlacementDecision
  selected device
  evidence
  rejected alternatives
  policy version
```

This is a roadmap shape, not Agate v2 schema text.

The important rule is that **observed hardware state is not itself policy**, and operator policy is not silently rewritten by runtime discovery.

## 7. Safety and hard constraints

MHS emphasizes that physical safety limits should exist independently of model behavior. Agate should adopt the analogous principle for local compute:

```text
agent/orchestrator preference
        |
        v
Agate placement evaluation
        |
        +-- allowed --> provider adapter
        |
        +-- forbidden --> refuse before load/dispatch
```

Examples of hard constraints include:

- model cannot fit within available memory/VRAM;
- required acceleration backend is absent;
- local-only policy forbids remote fallback;
- host/accelerator readiness is insufficient for placement.

Readiness is **fail-closed placement evidence**. If required host/accelerator readiness is missing,
stale beyond its declared validity window, or explicitly unavailable, Agate has insufficient
current evidence to approve placement and MUST refuse the placement. `--ignore-affinity` MUST NOT
turn missing, stale, or unavailable readiness into approval. Boundary tests MUST cover all three
states (missing, stale, unavailable) and prove that each remains denied both with and without the
affinity override.

Provider health and loaded-model state are not Agate-owned state. The provider adapter MUST still
refuse execution when its runtime is unhealthy or unavailable, even after Agate has approved the
hardware placement.

The existing GGUF RFC's `--ignore-affinity` override applies only to **Agate affinity enforcement**,
including the RFC's `NEVER` verdict. It MUST NOT disable independent hard resource checks such as
memory/VRAM fit, required-backend presence, or host/accelerator readiness, and it cannot override
provider/runtime health checks enforced by Claude-Desktop-LLM or another provider adapter.
Implementations SHOULD test these boundaries explicitly: the same request with
`--ignore-affinity` may bypass an affinity verdict, but MUST still fail each independent hard
constraint.

Where Agate distinguishes advisory affinity from hard safety/resource limits, the distinction must be explicit and testable.

## 8. MCP v2 is deliberately deferred

Claude-Desktop-LLM currently uses the MCP TypeScript v1 line. Its MCP v2 redesign MUST NOT begin until the Orama and Perpetua v2 migration into the `oramasys/*` repository family is **completed**, the resulting authority handoffs are explicit, and the target integration contracts are merged and authoritative.

This is a sequencing gate, not a soft preference.

Consequences:

- Agate does not design around MCP v2 today;
- Claude-Desktop-LLM should modernize its internal architecture without prematurely coupling to MCP v2 APIs;
- future MHS interoperability should not be forced through a speculative MCP v2 design;
- stdio/provider behavior remains independently testable during the deferral window;
- no compatibility shim should be introduced merely to anticipate an unfinished `oramasys/*` v2 contract.

## 9. OpenTelemetry is out of scope; provider-native observability is the target

OpenTelemetry is explicitly out of scope for Claude-Desktop-LLM **because observability should target Ollama and LM Studio directly at their provider/runtime boundaries**, rather than introducing a generic OpenTelemetry instrumentation/export pipeline between Claude-Desktop-LLM and those runtimes.

This is an **observability implementation rule only**. It does **not** change the Claude-Desktop-LLM architecture target. The canonical TypeScript implementation, tool registry, provider contract, provider adapters, policy boundaries, storage boundary, and strangler migration remain the intended architecture.

The observability direction is:

```text
canonical Claude-Desktop-LLM architecture
        |
        +--> Ollama adapter ------> Ollama native status / response / runtime observations
        |
        +--> LM Studio adapter ---> LM Studio native status / response / runtime observations
```

Accordingly:

- do not add an OpenTelemetry SDK, OTLP exporter, Collector topology, or generic telemetry provider lifecycle to Claude-Desktop-LLM;
- observe Ollama through its own runtime/API surfaces and response metadata;
- observe LM Studio through its own runtime/API surfaces and response metadata;
- normalize provider-native observations only where Claude-Desktop-LLM needs a common internal diagnostic view;
- do not make a local JSONL sink the observability authority or a substitute for provider-native runtime visibility;
- an optional local audit/debug record may exist if useful, but it is secondary evidence and MUST NOT redefine the architecture or become a second source of provider state;
- retain privacy/redaction boundaries for any data Claude-Desktop-LLM records or exposes.

Agate may define structured placement-decision evidence as ordinary data, but Agate MUST NOT require OpenTelemetry and does not own Claude-Desktop-LLM runtime observability.

## 10. MHS bridge policy when the standard stabilizes

If MHS becomes publicly normative, Agate should evaluate an **adapter/profile**, not a rewrite.

Preferred direction:

```text
Agate policy + local compute facts
        |
        v
optional MHS compute-profile adapter
        |
        v
MHS-compatible agent/device ecosystem
```

The adapter may translate Agate capability/state/policy concepts into the then-current MHS representation, but:

- Agate remains authoritative for OramaSys hardware policy;
- no silent dual writable source of truth is allowed;
- MHS transport/driver lifecycle should remain outside the core policy schema;
- compatibility must be proven against the actual published MHS specification and conformance tests available at that time.

## 11. Roadmap implications for all Agate planning

All future Agate plans should use the following framing unless explicitly superseded:

```text
Agate
  = hardware capability + affinity + routing authority
  = cold-local-metal compute/GPU subset
  = MHS-convergent, not presently MHS-conformant

Claude-Desktop-LLM
  = canonical local-model architecture with a provider contract
  = Ollama + LM Studio as canonical provider/runtime adapters
  = provider-native observability against Ollama + LM Studio directly
  = conceptual runtime companion to Agate

MCP v2
  = blocked until Orama + Perpetua v2 oramasys/* migration is complete
    and its contracts/authority handoffs are merged

OpenTelemetry
  = out of scope specifically for observability
  = MUST NOT be used as a reason to alter the architecture target

General robots/lab hardware
  = MHS domain, not Agate core scope
```

When an existing OramaSys plan says only that Agate owns "hardware capability/affinity/routing contracts," interpret that phrase using this narrower, more concrete local-metal definition.

## 12. Completion criterion

This positioning is successful when:

1. Agate can describe enough local compute capability and policy to make deterministic placement decisions before a provider call;
2. Claude-Desktop-LLM can consume those decisions without owning Agate's policy semantics;
3. Claude-Desktop-LLM retains its canonical TypeScript/tool-registry/provider-contract architecture while Ollama and LM Studio remain the two canonical runtime adapters;
4. provider health and loaded-model state remain provider-adapter authority rather than becoming Agate-owned state;
5. provider observability targets Ollama and LM Studio directly without requiring OpenTelemetry;
6. no MCP v2 dependency is required before the explicit migration gate opens;
7. an eventual MHS compute adapter can be added without replacing Agate or creating a second policy authority;
8. all claims of MHS compatibility are backed by the then-current public normative MHS specification rather than research-preview inference.
