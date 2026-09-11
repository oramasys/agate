import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  HardwareProfilesValidationError,
  parseHardwareProfileDatabase,
} from "../src/hardware_profiles.js";

const packagedProfiles = JSON.parse(
  readFileSync(new URL("../../../src/agate/data/hardware_profiles.json", import.meta.url), "utf8"),
) as unknown;

test("the packaged profile database validates through the canonical schema", () => {
  const database = parseHardwareProfileDatabase(packagedProfiles);

  assert.equal(database.version, 1);
  assert.ok(database.profiles.length > 0);
});

test("invalid profile data is rejected by the canonical schema", () => {
  assert.throws(
    () => parseHardwareProfileDatabase({ version: 1, profiles: [] }),
    HardwareProfilesValidationError,
  );
});

test("duplicate profile_id is rejected, mirroring the Python loader", () => {
  const [first] = (
    JSON.parse(
      readFileSync(
        new URL("../../../src/agate/data/hardware_profiles.json", import.meta.url),
        "utf8",
      ),
    ) as { profiles: Array<Record<string, unknown>> }
  ).profiles;
  const duplicate = { ...first };

  assert.throws(
    () => parseHardwareProfileDatabase({ version: 1, profiles: [first, duplicate] }),
    (error: unknown) =>
      error instanceof HardwareProfilesValidationError &&
      error.message.includes("uniquely named profiles"),
  );
});

test("an empty match object is rejected, mirroring the Python loader", () => {
  const packaged = JSON.parse(
    readFileSync(
      new URL("../../../src/agate/data/hardware_profiles.json", import.meta.url),
      "utf8",
    ),
  ) as { profiles: Array<Record<string, unknown>> };
  const emptyMatch = {
    ...packaged.profiles[0],
    profile_id: "empty-match-test",
    match: {},
  };

  // The canonical schema already expresses minProperties on `match`; the
  // loader-parity check in the binding is defense in depth for consumers that
  // bypass schema keywords. Either layer must reject the corpus.
  assert.throws(
    () => parseHardwareProfileDatabase({ version: 1, profiles: [emptyMatch] }),
    HardwareProfilesValidationError,
  );
});

