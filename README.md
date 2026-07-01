# supplyChainNexus

# Intelligent Global Supply Chain Risk Management

## Team

Vishnu Vardhan Reddy
Raghav
vicky

## Tech Stack

Python
FastAPI
Neo4j
Kafka
React
PostgreSQL
Docker
Azure OpenAI

## Architecture

External APIs / Mock Sources
        │
        ▼
 Ingestion Service
        │
        ▼
      Kafka
        │
 ┌──────┴────────┐
 ▼               ▼
Neo4j         PostgreSQL
(Graph)       (Risk Data)
 │               │
 └──────┬────────┘
        ▼
    Risk Engine
        │
        ▼
 GenAI Decision Engine
        │
        ▼
 FastAPI Backend
        │
        ▼
 React Dashboard
