# Canonical Event Schema

All platform events must use this envelope so producers and consumers can evolve independently.

## Required Envelope Fields

- `event_id` - globally unique identifier for the event.
- `event_type` - domain event name in dot notation, for example `supplier.created`.
- `event_version` - version of the business event contract.
- `schema_version` - version of the canonical envelope itself.
- `occurred_at` - UTC timestamp when the source system created the event.
- `source` - origin system metadata.
- `entity` - business entity type and id the event applies to.
- `tenant_id` - logical tenant or `global` when multi-tenancy is not in use.
- `correlation_id` - links events from the same workflow.
- `causation_id` - identifies the event that triggered this one.
- `trace_id` - distributed tracing correlation.
- `payload` - domain-specific body.
- `metadata` - free-form operational metadata.

## Source Object

```json
{
  "system": "supplier_erp",
  "service": "supplier-erp-mock",
  "environment": "local"
}
```

## Entity Object

```json
{
  "type": "supplier",
  "id": "2ebd1d5e-9b1f-49ad-9d57-2d4bd3f4d25b"
}
```

## Example Supplier Event

```json
{
  "event_id": "d9f6b21a-58b0-48c1-b1db-1e27d2c4a6db",
  "event_type": "supplier.created",
  "event_version": "1.0",
  "schema_version": "1.0",
  "occurred_at": "2026-07-03T10:15:30.123456+00:00",
  "ingested_at": null,
  "source": {
    "system": "supplier_erp",
    "service": "supplier-erp-mock",
    "environment": "local"
  },
  "entity": {
    "type": "supplier",
    "id": "2ebd1d5e-9b1f-49ad-9d57-2d4bd3f4d25b"
  },
  "tenant_id": "global",
  "correlation_id": "4f9d2d25-8c0a-49c0-9f6e-f0f3d5c0e4a1",
  "causation_id": "4f9d2d25-8c0a-49c0-9f6e-f0f3d5c0e4a1",
  "trace_id": "8c9e2b8b-5f5b-47bf-8a36-3d1f7c0bfc03",
  "payload": {
    "supplier_id": "2ebd1d5e-9b1f-49ad-9d57-2d4bd3f4d25b",
    "supplier_name": "Example Logistics Ltd.",
    "contact_email": "ops@example.com",
    "phone": "+1-555-0100",
    "country": "India",
    "status": "ACTIVE",
    "event_action": "CREATED"
  },
  "metadata": {
    "content_type": "application/json",
    "region": "IN"
  }
}
```

## Allowed Supplier Event Types

- `supplier.created`
- `supplier.updated`
- `supplier.deleted`

## Rules

- Producers must never emit ad hoc top-level fields outside the envelope.
- Consumers must treat unknown metadata as forward compatible.
- Version bumps must be documented before a consumer depends on them.