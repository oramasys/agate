# agate — Hardware Policy Specification

> `oramasys/agate` | MIT License | v1.0-alpha

**agate** is the open hardware affinity routing specification for local LLM deployments. It defines a portable YAML format and JSON Schema that any agent system — Python, JavaScript, Rust, Go, or any language — can consume to make hardware-aware routing decisions before dispatching LLM calls.

## Why agate exists

Running large language models locally is a hardware problem. A 27B parameter model that fits on a Windows RTX 3080 will OOM on a Mac with 8GB unified memory. An MLX-quantized model optimized for Apple Silicon runs an order of magnitude faster there than on a CPU-only shared host.

Today, every team that builds local-first AI tooling solves this problem in isolation — hardcoded `if platform == "darwin"` guards, ad-hoc JSON configs, magic environment variables. There is no shared language for expressing hardware intent.

**agate is that language.**

## Strategic direction: cold-local-metal compute

Agate's long-term role is the **cold-local-metal compute/GPU profile** of the OramaSys stack: operator-owned local compute, accelerator capability, model fit, affinity, and hard placement constraints.

The intended scope includes Apple Metal/MLX, NVIDIA CUDA, AMD ROCm, CPU/RAM fallback,
VRAM/unified-memory capacity, host/accelerator readiness required for placement, model placement,
and related compute state. Provider health, loaded-model state, and provider lifecycle remain
Claude-Desktop-LLM/runtime-adapter concerns. Agate does **not** expand into a general robotics,
laboratory-instrument, or physical-device automation framework.

Agate is being positioned to **converge conceptually with the compute-hardware subset of Anthropic's Model Hardware Standard (MHS)** as that research-preview specification matures. This is a direction of travel, not a claim of current MHS conformance. Agate v1 remains authoritative for its existing affinity contract until a public, stable MHS profile provides enough normative detail to justify a compatibility layer.

The conceptual bundle is:

```text
OramaSys policy / orchestration
          |
          v
Agate
  local-metal capability + affinity + hard placement constraints
          |
          v
Claude-Desktop-LLM
  canonical local-model control surface
          |
     +----+----+
     |         |
     v         v
  Ollama    LM Studio
     |         |
     +----+----+
          |
          v
CPU / Metal / CUDA / ROCm / local GPU memory
```

Agate answers **where a model may or should run**. Claude-Desktop-LLM answers **how the local model runtime is directly controlled** through canonical Ollama and LM Studio interfaces. Neither repository should absorb the other's authority.

See [`docs/mhs-local-metal-convergence.md`](docs/mhs-local-metal-convergence.md) for the convergence rules and deferred boundaries.

## The contract

```yaml
# model_hardware_policy.yml
version: 1
models:
  my-large-model:
    mac: NEVER      # too large for unified memory
    windows: PREFER # fits RTX 3080
    shared: ALLOW   # CPU fallback acceptable
routing:
  coding:default: my-large-model
  default: my-small-model
```

Three verdicts: `PREFER` | `ALLOW` | `NEVER`. One JSON Schema. Any runtime that validates against it can participate in the ecosystem.

## Quick start

```bash
# Validate your policy file
pip install jsonschema pyyaml
python -c "
import yaml, json, jsonschema
schema = json.load(open('schemas/model_hardware_policy.schema.json'))
policy = yaml.safe_load(open('my-policy.yml'))
jsonschema.validate(policy, schema)
print('Valid.')
"
```

## Schema

Full JSON Schema: [`schemas/model_hardware_policy.schema.json`](schemas/model_hardware_policy.schema.json)

Portable profile consumers should use
[`schemas/hardware_profiles.schema.json`](schemas/hardware_profiles.schema.json).
The reference TypeScript binding in
[`bindings/typescript/`](bindings/typescript/) validates data through that
schema rather than maintaining a second policy implementation.

Verdicts:
- `PREFER` — use this tier if available; it is the optimal target
- `ALLOW` — acceptable fallback; use if preferred tier unavailable  
- `NEVER` — hard forbidden; raises `HardwareAffinityError` at dispatch time

## Examples

- [`examples/lan-two-machine.yml`](examples/lan-two-machine.yml) — Mac orchestrator + Windows executor
- [`examples/single-mac.yml`](examples/single-mac.yml) — solo Mac with Ollama

## Scope guardrails

Agate owns hardware capability, affinity, model-fit, and routing contracts. It does not own:

- model inference APIs or provider-specific request formats;
- MCP versioning or transport semantics;
- OpenTelemetry exporters;
- graph scheduling or agent orchestration;
- laboratory/robotics device drivers;
- cloud placement as the default architecture.

Future MHS interoperability, if adopted, should be an adapter/profile over the stable Agate contract rather than a second writable source of hardware policy truth.

## Implementation status

`src/agate/` is the first real implementation of this contract: loading a
schema-conformant `model_hardware_policy.yml`, resolving a named physical
profile (the portable `src/agate/data/hardware_profiles.json` catalog holds the
three proven fleet profiles — mac-studio, win-rtx3080, win-rtx5080) against a
model, and returning
`PREFER`/`ALLOW`/`NEVER` with fail-closed behavior for unknown models.
The default policy is packaged in the wheel. In a source checkout,
`config/model_hardware_policy.yml` is a relative compatibility symlink to
`src/agate/data/model_hardware_policy.yml`, so both paths always read one
canonical policy. Preserve symlink support when cloning on Windows. For
deployment-specific edits, copy the canonical YAML to an operator-controlled
path and pass that path to `load_policy(path)`. Set `AGATE_PROFILE_DATABASE` to
an operator-maintained JSON catalog when the local fleet differs from the
packaged defaults.

`observe_local_hardware()` collects local, best-effort physical evidence without
provider or network I/O. `identify_profile()` only returns a profile when that
evidence matches every configured identity field; incomplete or conflicting
evidence returns `None` rather than guessing. This keeps runtime observation,
operator-editable specifications, and model-fit policy separate.

On Windows, observation uses local PowerShell/CIM queries with `-NoProfile` and
`-NonInteractive`. Failed commands, malformed output, and unusable capacity
values yield incomplete evidence rather than a profile claim. A real Windows
canary remains an operator-run evidence step; automated tests use only synthetic
command output.

Explicitly not yet implemented, because the design decisions they depend
on are genuinely open, not because they were forgotten:

- **The "too small / overqualified" verdict** (`PROFILE_UNDERUSE`). No
  numeric threshold or scoping rule has been decided — this needs the
  repo owner's input, not an invented default.
- **Machine-level concurrency/thermal safety.** The mac-studio
  concurrent-heavy-engine prohibition is preserved in portable profile data,
  but its admission/capacity enforcement remains a separate policy plane.
- **win-rtx3080 vs win-rtx5080** currently resolve to the same schema
  verdict tier (`windows`) — the v1 schema has no way to express them as
  separately-verdicted identities. A real, open question for a future
  schema v2, not silently worked around.

## Spec versioning

agate uses integer version numbers in the `version` field. Schema version 1 is the initial release. Breaking changes bump to version 2. Additive changes (new optional fields) do not bump the version.

## License

MIT. Use it, fork it, publish policies as open standards.
