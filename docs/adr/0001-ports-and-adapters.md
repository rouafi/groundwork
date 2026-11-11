# 0001. Ports and adapters

Status: accepted

## Context
Every client runs a different SaaS stack (HubSpot, Salesforce...). The core must not change when the stack changes.

## Decision
Hexagonal architecture: the core depends only on ports; adapters implement them; entrypoints wire them. Client packs select adapters in config. Enforced with import-linter.

## Consequences
New SaaS = one adapter + contract tests + one config line. Slight indirection cost, accepted.
