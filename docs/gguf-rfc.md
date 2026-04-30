# RFC: GGUF Hardware Affinity Metadata Extension (agate v1)

**Status:** Draft — Community Review  
**Author:** oramasys / diazMelgarejo  
**Repository:** https://github.com/oramasys/agate  
**Schema:** https://github.com/oramasys/agate/schemas/model_hardware_policy.schema.json  
**Date:** 2026-04-30  
**RFC Keywords:** The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## Quick Reference (for implementers)

| Key | Type | Values | Required? |
|-----|------|--------|-----------|
| `agate.version` | `u32` | `1` | Yes (if any agate.* key present) |
| `agate.mac` | `str` | `PREFER` \| `ALLOW` \| `NEVER` | No |
| `agate.windows` | `str` | `PREFER` \| `ALLOW` \| `NEVER` | No |
| `agate.shared` | `str` | `PREFER` \| `ALLOW` \| `NEVER` | No |
| `agate.context` | `u32` | token count | No |
| `agate.roles` | `str` | comma-separated list | No |
| `agate.notes` | `str` | human-readable text | No |
| `agate.schema_url` | `str` | URL | No |

**Absent key rule:** If a tier key is absent, runners MUST treat it as `ALLOW`.  
**NEVER rule:** If a tier key is `NEVER`, runners MUST refuse to load the model on that tier and display the affinity error.  
**Override:** Runners SHOULD provide `--ignore-affinity` to bypass for advanced users.

---

## Abstract

This RFC proposes a set of GGUF metadata keys under the `agate.*` namespace that embed hardware affinity verdicts directly in a model file. A verdict declares whether a model PREFERS, ALLOWS, or must NEVER run on a given hardware tier (`mac`, `windows`, `shared`). Runners (llama.cpp, Ollama, LM Studio, koboldcpp, and others) that implement this extension can enforce hardware routing at model-load time — no separate configuration file required.

The extension is additive and fully backward-compatible. Existing GGUF files without `agate.*` keys behave identically to today.

---

## 1. Motivation

### 1.1 The drift problem

Running large language models locally is a hardware problem before it is a software problem. A 27B-parameter model that saturates an NVIDIA RTX 3080's 24GB VRAM will out-of-memory-kill a Mac with 8GB unified memory. An MLX-quantized model optimized for Apple Silicon runs an order of magnitude faster there than on a CPU-only Linux host.

Today, every team that builds local-first AI tooling expresses this constraint differently:

- `if platform.system() == "darwin":` guards in launcher scripts
- Environment variables (`OLLAMA_GPU_LAYERS`, `LM_STUDIO_FORCE_CPU`)
- Separate YAML/JSON config files that must be maintained alongside the model file
- Tribal knowledge ("don't run 27B on the Mac, it OOMs") that doesn't travel with the model

**When a user copies a `.gguf` file to a new machine, they lose the hardware context that should accompany it.**

### 1.2 The proposal

This RFC proposes embedding hardware affinity directly in the GGUF metadata block. The affinity travels with the model file — to new machines, to shared network drives, to Hugging Face downloads. A runner that implements this extension can refuse to load a model on incompatible hardware before allocating any memory, surfacing a clear error rather than an OOM crash.

### 1.3 Relationship to agate

The [agate specification](https://github.com/oramasys/agate) defines a portable YAML/JSON hardware affinity contract for local LLM deployments. This RFC defines how to embed the same verdicts in GGUF files. The two are complementary:

- **agate policy file** (`model_hardware_policy.yml`): fleet-level routing for multiple models across a LAN
- **GGUF agate extension** (this RFC): per-model affinity embedded in the file itself

When both are present, the policy file takes precedence (it reflects the operator's intent for their specific deployment).

---

## 2. GGUF Background

GGUF (GPT-Generated Unified Format) is the model file format used by llama.cpp and most local inference runtimes. Its structure is:

```
magic number (4 bytes)
version (u32)
tensor count (u64)
metadata kv count (u64)
metadata key-value pairs...
tensor info blocks...
tensor data...
```

Each metadata key-value pair is:

```
key_length (u64)
key (utf-8 string)
value_type (u32: 0=u8, 1=i8, 4=u32, 8=str, ...)
value (type-specific encoding)
```

The GGUF spec explicitly reserves no namespace, and third-party namespaces are common practice (`llama.*`, `tokenizer.*`, `general.*`). The `agate.*` namespace follows this convention.

---

## 3. Extension Specification

### 3.1 Namespace

All keys defined in this RFC use the prefix `agate.`. No other key prefix is defined here.

### 3.2 Normative keys

#### `agate.version` (u32) — REQUIRED if any `agate.*` key is present

The version of the agate GGUF extension schema. This RFC defines version `1`.

Runners encountering an `agate.version` value greater than they support SHOULD treat all `agate.*` keys as if absent (fallback to ALLOW) and MUST emit a warning:

```
Warning: agate.version=N is unsupported (this runner supports up to version 1).
Treating all hardware affinity keys as ALLOW.
```

#### `agate.mac` (str) — OPTIONAL

Hardware affinity verdict for Apple Silicon (Mac) hardware.

#### `agate.windows` (str) — OPTIONAL

Hardware affinity verdict for Windows hardware (typically NVIDIA GPU via CUDA).

#### `agate.shared` (str) — OPTIONAL

Hardware affinity verdict for shared or CPU-only hardware (any platform, no dedicated GPU).

#### Verdict values

Each tier key MUST contain exactly one of:

| Verdict | Meaning |
|---------|---------|
| `PREFER` | This tier is the optimal hardware target for this model. Runners SHOULD select it when available. |
| `ALLOW` | This tier is an acceptable target. The model will run but may not be optimal. |
| `NEVER` | This tier is forbidden. Runners MUST refuse to load the model on this tier. |

Any other value MUST be treated as `ALLOW`. Runners SHOULD emit a warning when encountering an unrecognized verdict:

```
Warning: agate.mac has unrecognized value "MAYBE". Treating as ALLOW.
```

### 3.3 Informational keys

These keys carry metadata. Runners MAY use them for display, logging, or routing hints but are not required to enforce any behavior based on them.

#### `agate.context` (u32) — OPTIONAL

The model's designed context window size in tokens. This is informational — runners already know this from `llama.context_length`. Included for tooling that reads agate keys without a full GGUF parser.

#### `agate.roles` (str) — OPTIONAL

Comma-separated list of semantic roles this model is suited for. Examples: `"orchestrator,final-validator"`, `"coder,checker,refiner"`, `"fallback"`. No controlled vocabulary is defined in v1; this is freeform for human consumption.

#### `agate.notes` (str) — OPTIONAL

Human-readable rationale for the affinity rules. Example: `"Too large for Mac unified memory (8GB). RTX 3080 24GB on Windows handles this at full precision."`.

#### `agate.schema_url` (str) — OPTIONAL

URL to the canonical agate JSON Schema for validation. Intended value: `"https://github.com/oramasys/agate/schemas/model_hardware_policy.schema.json"`. Tooling MAY use this to locate the schema for offline validation.

---

## 4. Runner Behavior (normative)

### 4.1 Detecting the current hardware tier

Runners MUST determine their hardware tier before evaluating affinity:

- **`mac`**: Running on Apple Silicon (arm64 macOS) with MLX or Metal acceleration.
- **`windows`**: Running on Windows with CUDA or ROCm GPU acceleration.
- **`shared`**: Running on any platform in CPU-only mode, or on Linux without the above.

Runners MAY extend this taxonomy for future tiers (e.g., `cloud`, `linux_cuda`) — this is a v2 concern. For v1, unknown tiers fall through to `ALLOW`.

### 4.2 Evaluation algorithm

```
function evaluate_affinity(model_file, current_tier):
    if "agate.version" not in model_file.metadata:
        return ALLOW          # no agate extension — backward compat
    
    version = model_file.metadata["agate.version"]
    if version > SUPPORTED_VERSION:
        warn("agate.version={version} unsupported; treating all tiers as ALLOW")
        return ALLOW
    
    key = f"agate.{current_tier}"
    if key not in model_file.metadata:
        return ALLOW          # absent key = ALLOW
    
    verdict = model_file.metadata[key].strip().upper()
    if verdict not in ("PREFER", "ALLOW", "NEVER"):
        warn(f"{key} has unrecognized value {verdict!r}; treating as ALLOW")
        return ALLOW
    
    return verdict
```

### 4.3 Enforcement

| Verdict | Required runner action |
|---------|------------------------|
| `PREFER` | Load normally. Runners MAY display "optimal hardware" indicator. |
| `ALLOW` | Load normally. |
| `NEVER` | MUST refuse to load. MUST display: `Error: model '{name}' is marked NEVER for {tier} hardware (agate.{tier}=NEVER). Use --ignore-affinity to override.` |

### 4.4 User override

Runners SHOULD provide a `--ignore-affinity` flag (or equivalent) that bypasses `NEVER` enforcement. This prevents a denial-of-service scenario where a malicious or misconfigured `.gguf` file sets `NEVER` on all tiers.

When `--ignore-affinity` is active, runners SHOULD log:

```
Warning: hardware affinity enforcement disabled (--ignore-affinity). agate.{tier}=NEVER for this model.
```

---

## 5. Reference Implementation

A minimal Python snippet for reading `agate.*` keys from a GGUF file (requires only the standard library plus a GGUF parser):

```python
"""Read agate hardware affinity keys from a GGUF file."""
import struct
from pathlib import Path
from typing import Literal

Verdict = Literal["PREFER", "ALLOW", "NEVER"]
Tier = Literal["mac", "windows", "shared"]

GGUF_MAGIC = b"GGUF"
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_STRING = 8


def _read_string(f) -> str:
    length = struct.unpack("<Q", f.read(8))[0]
    return f.read(length).decode("utf-8")


def _read_value(f, value_type: int):
    if value_type == GGUF_TYPE_UINT32:
        return struct.unpack("<I", f.read(4))[0]
    elif value_type == GGUF_TYPE_STRING:
        return _read_string(f)
    else:
        raise ValueError(f"Unsupported GGUF value type for agate keys: {value_type}")


def read_agate_keys(gguf_path: str | Path) -> dict:
    """Return all agate.* metadata keys from a GGUF file."""
    keys = {}
    with open(gguf_path, "rb") as f:
        if f.read(4) != GGUF_MAGIC:
            raise ValueError("Not a valid GGUF file")
        _version = struct.unpack("<I", f.read(4))[0]
        n_tensors = struct.unpack("<Q", f.read(8))[0]
        n_kv = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n_kv):
            key = _read_string(f)
            value_type = struct.unpack("<I", f.read(4))[0]
            value = _read_value(f, value_type)
            if key.startswith("agate."):
                keys[key] = value
    return keys


def get_verdict(gguf_path: str | Path, tier: Tier) -> Verdict:
    """Return the affinity verdict for the given hardware tier."""
    keys = read_agate_keys(gguf_path)
    if "agate.version" not in keys:
        return "ALLOW"
    raw = keys.get(f"agate.{tier}", "ALLOW")
    verdict = str(raw).strip().upper()
    return verdict if verdict in ("PREFER", "ALLOW", "NEVER") else "ALLOW"


# Example usage
if __name__ == "__main__":
    path = "my_model.gguf"
    verdict = get_verdict(path, tier="mac")
    print(f"agate verdict for mac: {verdict}")
    if verdict == "NEVER":
        print("This model is not compatible with Mac hardware.")
```

> **Note:** This is a teaching implementation. A production GGUF parser must handle all GGUF value types, array types, and version differences. See [gguf-py](https://github.com/ggml-org/llama.cpp/tree/master/gguf-py) for the reference Python implementation.

---

## 6. Embedding agate Keys in a GGUF File

To add agate keys to an existing GGUF file, use the `gguf-py` library from the llama.cpp repository:

```python
from gguf import GGUFWriter

writer = GGUFWriter("output_model.gguf", arch="llama")
# ... add tensors from existing file ...

# Add agate affinity keys
writer.add_uint32("agate.version", 1)
writer.add_string("agate.mac", "NEVER")      # too large for Mac unified memory
writer.add_string("agate.windows", "PREFER") # RTX 3080 24GB — optimal
writer.add_string("agate.shared", "ALLOW")   # CPU-only fallback acceptable
writer.add_uint32("agate.context", 16384)
writer.add_string("agate.roles", "coder,checker,refiner")
writer.add_string("agate.notes", "Distilled 27B; requires 16GB+ VRAM for full precision")

writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_tensors_to_file()
writer.close()
```

> **Tooling note:** A CLI tool `agate-stamp` for non-destructively adding/updating `agate.*` keys to existing GGUF files is planned as a separate project. Contributions welcome at https://github.com/oramasys/agate.

---

## 7. Backward Compatibility

This extension is strictly additive:

- Runners that do not implement this RFC ignore all `agate.*` keys (they are legal GGUF metadata)
- GGUF files without `agate.*` keys behave identically to today
- Runners implementing this RFC treat absent keys as `ALLOW`, preserving existing behavior

No breaking changes to the GGUF format, no version bump of the GGUF format itself.

---

## 8. Security Considerations

### 8.1 Tampering

GGUF metadata is not cryptographically signed. An `agate.*` verdict in a GGUF file carries no more trust authority than the file itself. Do not rely on `agate.*` verdicts for security-sensitive decisions (e.g., preventing a model from running in a compliance context) without additional verification out of band.

For compliance enforcement, use an operator-controlled `model_hardware_policy.yml` that overrides per-file affinity. See the [agate specification](https://github.com/oramasys/agate).

### 8.2 Denial-of-service via NEVER

A malicious or misconfigured GGUF file could set `NEVER` on all tiers, causing the runner to refuse to load the model anywhere. Runners MUST:

1. Display the affinity values when refusing to load, so users can diagnose the issue
2. Provide `--ignore-affinity` (or equivalent) to bypass enforcement

### 8.3 Path traversal in `agate.schema_url`

If a runner fetches the URL in `agate.schema_url` for validation, it MUST treat this URL as untrusted input and apply standard URL validation. Runners SHOULD only fetch `https://` URLs from trusted domains.

---

## 9. FAQ

**Q: Why `mac`, `windows`, `shared` and not GPU-specific tiers like `cuda`, `metal`, `rocm`?**

The agate v1 vocabulary is intentionally coarse — it maps to the deployment realities of the most common local AI setups (Apple Silicon Mac, Windows + NVIDIA GPU, everything else). Finer-grained tiers (CUDA compute capability, specific VRAM sizes) are a v2 concern. The goal of v1 is to cover the 80% case with the simplest possible vocabulary.

**Q: What if I want to use agate keys for cloud tiers (AWS GPU, Modal, RunPod)?**

This is planned for agate GGUF v2. For now, cloud tiers are out of scope. Use a separate `model_hardware_policy.yml` with custom tier keys for cloud routing.

**Q: How does this interact with quantization level?**

Quantization already affects which hardware can run a model (a Q8_0 27B needs more VRAM than a Q4_K_M 27B). The `agate.*` keys should reflect the specific quantized file's hardware requirements, not the base model's requirements. A Q4_K_M of a 27B model might have `agate.mac=ALLOW` while the same model at Q8_0 has `agate.mac=NEVER`.

**Q: Who sets the verdicts — the model publisher or the runner?**

The model publisher sets them at time of quantization, where hardware requirements are known. Runners read and enforce them. Operators can override via `model_hardware_policy.yml` for their specific deployment.

**Q: Should PREFER tiers be mutually exclusive?**

No. A model can PREFER both `mac` and `windows` (e.g., it runs well on both with appropriate quantization). The runner picks the first available PREFER tier.

**Q: My GGUF file doesn't have agate keys yet. Can runners infer the verdicts?**

Runners MAY infer verdicts based on model size and quantization metadata (e.g., auto-set `NEVER` for mac if `llama.context_length > 4096` AND model size exceeds available unified memory). This is out of scope for this RFC — inference is runner-specific policy, not a shared standard.

---

## 10. Community Process

This RFC is in **Draft** status. Feedback is welcome via:

- **GitHub Issues:** https://github.com/oramasys/agate/issues
- **GitHub Discussions:** https://github.com/oramasys/agate/discussions
- **llama.cpp Issues:** Tag `[agate-rfc]` in the llama.cpp issue tracker
- **r/LocalLLaMA:** Post with flair `[RFC]`

To move to **Proposed** status, this RFC needs:
- [ ] Implementation in at least one runner (llama.cpp, Ollama, or LM Studio) — draft PR or proof-of-concept
- [ ] Feedback from at least 3 distinct runner/tooling authors
- [ ] Review from the llama.cpp maintainers on GGUF metadata conventions

To move to **Accepted** status:
- [ ] Merged implementation in llama.cpp (the reference GGUF implementation)
- [ ] Consensus from Ollama and/or LM Studio teams on the key names and verdict semantics

---

## Appendix A: Full Example

A GGUF file representing the `Qwen3.5-27B-Distilled` model quantized to Q4_K_M with agate keys embedded:

```
agate.version  = 1          (u32)
agate.mac      = "NEVER"    (str) — 27B Q4_K_M requires ~15GB; exceeds Mac 8GB unified memory
agate.windows  = "PREFER"   (str) — RTX 3080 24GB is the reference hardware
agate.shared   = "ALLOW"    (str) — CPU-only is slow but functional
agate.context  = 16384      (u32)
agate.roles    = "coder,checker,refiner,executor,verifier"  (str)
agate.notes    = "Distilled from Qwen3.5-27B. Requires 16GB+ VRAM for optimal batch size. CPU inference ~3 tok/s on M2 Pro."  (str)
agate.schema_url = "https://github.com/oramasys/agate/schemas/model_hardware_policy.schema.json"  (str)
```

---

## Appendix B: Comparison with Alternative Approaches

| Approach | Affinity travels with model | No runner changes needed | Standardizable |
|----------|----------------------------|-------------------------|----------------|
| **GGUF agate extension (this RFC)** | ✅ Yes | ❌ Requires runner update | ✅ Yes |
| Sidecar file (`.gguf.agate.yml`) | ⚠️ Only if copied together | ✅ Yes (external tooling) | ✅ Yes |
| `model_hardware_policy.yml` (agate v1) | ❌ No | ✅ Yes | ✅ Yes |
| Hardcoded runner logic | ❌ No | ✅ Yes (already present) | ❌ No |

The GGUF extension approach has the highest long-term value (affinity travels with the model) at the cost of requiring runner updates. The sidecar file approach is a viable interim for tooling authors who cannot modify their runner.

---

*Draft RFC | oramasys/agate | 2026-04-30 | MIT License*
