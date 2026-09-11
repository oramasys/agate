# Agate TypeScript Hardware-Profile Binding

This small binding exposes typed hardware-profile data for TypeScript consumers.
It delegates validation to Agate's canonical Draft 2020-12 JSON Schema at
`schemas/hardware_profiles.schema.json`; it does not reimplement policy,
profile matching, or hardware observation.

The companion editable policy template remains YAML at
`config/model_hardware_policy.yml`. JSON profile data and YAML policy have
separate responsibilities and are not interchangeable authorities.

```sh
npm install
npm test
npm run typecheck
```
