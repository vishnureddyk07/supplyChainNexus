# Service Boundaries

## Ingestion Service

Responsibilities:

- Accept payloads from mocks or external integrations.
- Validate against the canonical event schema.
- Publish normalized events to Kafka.
- Reject malformed events early.

Non-responsibilities:

- No graph persistence.
- No risk scoring.
- No UI-facing logic.

## Graph Service

Responsibilities:

- Consume canonical events.
- Maintain entity and relationship projections in Neo4j.
- Provide graph-oriented lookup capabilities.

Non-responsibilities:

- No UI rendering.
- No source-system ingestion.
- No authoritative risk decision-making.

## Risk API

Responsibilities:

- Serve read APIs for operational dashboards and downstream automation.
- Aggregate data from PostgreSQL and Neo4j.
- Expose risk alerts, entity status, and recommendation summaries.

Non-responsibilities:

- No direct event production.
- No storage ownership for raw source events.

## GenAI Service

Responsibilities:

- Turn risk context into concise explanations and recommended actions.
- Offer prompt orchestration and structured narrative generation.

Non-responsibilities:

- No canonical data storage.
- No hard business-rule ownership.

## Frontend

Responsibilities:

- Present operational views, alerts, and investigations.
- Call the Risk API only.

Non-responsibilities:

- No direct database access.
- No event publishing.

## Mock Sources

Responsibilities:

- Generate realistic test data for development and demos.
- Mimic upstream ERP and sensor systems.

Non-responsibilities:

- No business logic beyond test data generation.