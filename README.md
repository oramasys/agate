# agate — Hardware Policy Specification

> `oramasys/agate` | MIT License | v1.0-alpha

**agate** is the open hardware affinity routing specification for local LLM deployments. It defines a portable YAML format and JSON Schema that any agent system — Python, JavaScript, Rust, Go, or any language — can consume to make hardware-aware routing decisions before dispatching LLM calls.

## Why agate exists

Running large language models locally is a hardware problem. A 27B parameter model that fits on a Windows RTX 3080 will OOM on a Mac with 8GB unified memory. An MLX-quantized model optimized for Apple Silicon runs an order of magnitude faster there than on a CPU-only shared host.

Today, every team that builds local-first AI tooling solves this problem in isolation — hardcoded `if platform == "darwin"` guards, ad-hoc JSON configs, magic environment variables. There is no shared language for expressing hardware intent.

**agate is that language.**

## Strategic direction: cold-local-metal compute

Agate's long-term role is the **cold-local-metal compute/GPU profile** of the OramaSys stack: operator-owned local compute, accelerator capability, model fit, affinity, and hard placement constraints.

The intended scope includes Apple Metal/MLX, NVIDIA CUDA, AMD ROCm, CPU/RAM fallback, VRAM/unified-memory capacity, local runtime availability, model placement, and related compute state. It does **not** expand Agate into a general robotics, laboratory-instrument, or physical-device automation framework.

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

## Spec versioning

agate uses integer version numbers in the `version` field. Schema version 1 is the initial release. Breaking changes bump to version 2. Additive changes (new optional fields) do not bump the version.

## License

MIT. Use it, fork it, publish policies as open standards.
