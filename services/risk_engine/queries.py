"""Parameterized Cypher queries used by API and Risk Engine consumers.

Inputs are company IDs. Dependency traversal is intentionally hard-capped at
five hops in both the query and wrapper, preventing unbounded graph scans.
"""

from __future__ import annotations

from typing import Any, Protocol

from .models import AlternativeSupplier, AlternativeSupplierResponse, BlastRadiusResponse, DependencyNode, DependencyResponse

MAX_HOPS = 5
DEPENDENCY_TRAVERSAL = """
MATCH (root:Company {company_id: $company_id})
MATCH path=(root)-[:SUPPLIES*1..5]->(dependent:Company)
WITH dependent, min(length(path)) AS tier
RETURN dependent.company_id AS company_id, dependent.name AS name, tier
ORDER BY tier, company_id
LIMIT $limit
"""

CASCADE_COUNT = """
MATCH (failed:Company {company_id: $company_id})
MATCH (failed)-[:SUPPLIES*1..5]->(affected:Company)
RETURN count(DISTINCT affected) AS affected_count,
       collect(DISTINCT affected.company_id)[..$limit] AS affected_company_ids
"""

ALTERNATIVE_SUPPLIERS = """
MATCH (alternative:Company)-[:ALTERNATIVE_FOR]->(target:Company {company_id: $company_id})
RETURN alternative.company_id AS company_id, alternative.name AS name, alternative.country AS country
ORDER BY alternative.name, alternative.company_id
LIMIT $limit
"""


class QuerySession(Protocol):
    async def execute_read(self, transaction_function: Any, *args: Any, **kwargs: Any) -> Any: ...


class GraphQueryService:
    def __init__(self, driver: Any, timeout_seconds: float = 5.0, result_limit: int = 500) -> None:
        if result_limit < 1:
            raise ValueError("result_limit must be positive")
        self.driver = driver
        self.timeout_seconds = timeout_seconds
        self.result_limit = result_limit

    async def _run(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        import asyncio

        async def read() -> list[dict[str, Any]]:
            async with self.driver.session() as session:
                result = await session.run(query, **params)
                return [record.data() async for record in result]

        return await asyncio.wait_for(read(), timeout=self.timeout_seconds)

    async def dependencies(self, company_id: str, max_hops: int = MAX_HOPS) -> DependencyResponse:
        if not 1 <= max_hops <= MAX_HOPS:
            raise ValueError(f"max_hops must be between 1 and {MAX_HOPS}")
        rows = await self._run(DEPENDENCY_TRAVERSAL, {"company_id": company_id, "limit": self.result_limit})
        return DependencyResponse(root_company_id=company_id, nodes=[DependencyNode(**row) for row in rows])

    async def cascade_count(self, company_id: str) -> BlastRadiusResponse:
        rows = await self._run(CASCADE_COUNT, {"company_id": company_id, "limit": self.result_limit})
        row = rows[0] if rows else {"affected_count": 0, "affected_company_ids": []}
        return BlastRadiusResponse(company_id=company_id, **row)

    async def alternatives(self, company_id: str) -> AlternativeSupplierResponse:
        rows = await self._run(ALTERNATIVE_SUPPLIERS, {"company_id": company_id, "limit": self.result_limit})
        return AlternativeSupplierResponse(company_id=company_id, alternatives=[AlternativeSupplier(**row) for row in rows])
