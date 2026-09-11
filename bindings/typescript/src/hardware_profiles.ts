import Ajv2020 from "ajv/dist/2020.js";
import { type ErrorObject } from "ajv/dist/2020.js";

import hardwareProfilesSchema from "../../../schemas/hardware_profiles.schema.json" with { type: "json" };

export type VerdictTier = "mac" | "windows" | "shared";

export interface HardwareProfileMatch {
  os?: string;
  cpu_contains?: string;
  accelerator_contains?: string;
  ram_gb?: number;
  accelerator_memory_gb?: number;
}

export interface HardwareProfile {
  profile_id: string;
  role: string;
  verdict_tier: VerdictTier;
  os: string;
  cpu: string;
  ram_gb: number;
  accelerator: string;
  accelerator_memory_gb: number;
  notes?: string[];
  match: HardwareProfileMatch;
}

export interface HardwareProfileDatabase {
  version: 1;
  profiles: HardwareProfile[];
}

export class HardwareProfilesValidationError extends Error {
  public constructor(details: string) {
    super(`Invalid hardware-profile database: ${details}`);
    this.name = "HardwareProfilesValidationError";
  }
}

const validate = new Ajv2020({ allErrors: true, strict: true }).compile<HardwareProfileDatabase>(
  hardwareProfilesSchema,
);

/**
 * Validate operator data through Agate's canonical JSON Schema.
 *
 * This binding deliberately does not duplicate Python's policy or matching
 * logic. Consumers receive typed data only after the shared schema accepts it.
 *
 * Cross-field rules the schema cannot express are mirrored from
 * `src/agate/profiles.py` (`load_profile_store`) so the binding accepts and
 * rejects exactly the same corpus as the Python loader:
 * - profile_id uniqueness across the database
 * - a non-empty `match` object on every profile
 */
export function parseHardwareProfileDatabase(value: unknown): HardwareProfileDatabase {
  if (!validate(value)) {
    const details = (validate.errors ?? [])
      .map((error: ErrorObject) => `${error.instancePath || "/"} ${error.message ?? "invalid"}`)
      .join("; ");
    throw new HardwareProfilesValidationError(details || "schema validation failed");
  }

  const database = value as HardwareProfileDatabase;
  const seen = new Set<string>();
  for (const profile of database.profiles) {
    if (seen.has(profile.profile_id)) {
      throw new HardwareProfilesValidationError(
        `profile database must contain uniquely named profiles: duplicate profile_id ${JSON.stringify(profile.profile_id)}`,
      );
    }
    seen.add(profile.profile_id);
    if (Object.keys(profile.match).length === 0) {
      throw new HardwareProfilesValidationError(
        `invalid hardware profile match constraints: profile ${JSON.stringify(profile.profile_id)} has an empty match object`,
      );
    }
  }
  return database;
}

