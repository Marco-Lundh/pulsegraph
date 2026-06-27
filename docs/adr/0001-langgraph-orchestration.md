# ADR 0001: Use LangGraph as the orchestration framework

## Status
Accepted

## Context
The project is a production system for AI agent orchestration. The requirement is for the system to mirror a real production environment — with state management, checkpoints, error recovery, and traceability — not merely to chain LLM calls together.

A market survey (June 2026) showed that the leading frameworks for multi-agent orchestration are LangGraph, CrewAI, AutoGen/AG2, the OpenAI Agents SDK, and Google ADK.

## Decision
We build the agent pipeline on **LangGraph**.

Rationale:
- LangGraph overtook CrewAI in GitHub stars during 2026, driven by enterprise adoption and its graph-based architecture, which fits production requirements such as audit trails and rollback points.
- The orchestration model is an explicit directed graph with conditional edges — agents, tools, and checkpoints are nodes, and transitions are edges. This gives exactly the control and traceability we need for error handling and eval.
- Built-in state persistence with checkpointing and "time travel" debugging maps directly onto the requirement for rollback points.
- It is model-agnostic — it does not lock us into a specific LLM provider, which matters because we run both a local model (Ollama) and a cloud model (Claude).

## Alternatives considered
- **CrewAI** — faster to get started with (a role-based DSL, ~20 lines for a first crew), but in production its architecture is described as rigid and hard to debug: you cannot clearly see what is actually sent to the LLM, and the abstraction becomes opaque at scale. Unsuitable when error handling and debuggability are central requirements.
- **AutoGen/AG2** — stronger for conversational multi-agent research, less suited to a deterministic pipeline with well-defined steps.
- **OpenAI Agents SDK / Google ADK** — lock in to a specific model provider (OpenAI and Gemini respectively), which conflicts with the requirement for local+cloud routing.

## Consequences
- **Easier:** traceability, checkpointing, time-travel debugging, integration with LangSmith for observability (see ADR 0007).
- **Harder:** more boilerplate than CrewAI for simple flows — a basic ReAct agent takes more lines of code. This is a deliberate trade-off: we pay in code to gain control.
- Documented in the README as a deliberate choice (CrewAI as a "considered alternative") to make the decision process traceable.
