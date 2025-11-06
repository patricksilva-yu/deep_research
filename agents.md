# Overview

- Deep Research (DR) multi-agent systems comprise multiple specialized agents for complex research workflows.
- Agents specialize in planning, execution, tool invocation, information retrieval, and synthesis.
- Coordination uses hierarchical or centralized planning (e.g., manager/coordinator agents) to modularize subtasks.

## Agent Types

### 1) Planner (Coordinator/Manager)
- Capabilities:
  - Decompose user queries into subtasks
  - Allocate and reassign tasks to agents
  - Manage real-time feedback and replanning
- Tools:
  - Workflow orchestration modules
  - Centralized scheduling interfaces
  - Agent-to-Agent (A2A) communication protocols

### 2) Execution Agents (Specialists)
- Capabilities:
  - Perform retrieval, extraction, code execution, analysis, or synthesis
  - Execute tasks from the coordinator's plan
  - Integrate results into shared workflow or memory
- Tools:
  - Function-specific toolkits (retrieval APIs, browsers, code interpreters)
  - Multimodal handlers for text, image, and code

### 3) Tool Caller / Invoker
- Capabilities:
  - Interface with external tools and data sources
  - Dynamically invoke APIs, browsers, and databases
  - Ensure up-to-date knowledge acquisition
- Tools:
  - Model Context Protocol (MCP)
  - API connectors, headless browsers, database clients

### 4) Retrieval / Browser Agents
- Capabilities:
  - Conduct web/API search and retrieval
  - Interact with dynamic web pages and structured repositories
  - Aggregate, filter, and preprocess information
- Tools:
  - Search engine APIs
  - Programmatic browsers (e.g., Browserbase, headless)
  - Scraping and preprocessing modules

### 5) Data Analytics / Analysis Agents
- Capabilities:
  - Turn raw outputs into structured insights
  - Perform statistics, charts, tables, and visualizations
  - Support quantitative reasoning and hypothesis testing
- Tools:
  - Data libraries (Python, SQL, R)
  - Visualization toolkits
  - Local or remote computation modules

### 6) Code Interpreter Agents
- Capabilities:
  - Execute scripts/code in workflows
  - Support algorithmic reasoning, simulation, and verification
  - Automate literature-driven analysis and real-time computation
- Tools:
  - Code interpreter environments (e.g., Python, Java)
  - Script orchestration utilities

### 7) Multimodal Processing Agents
- Capabilities:
  - Integrate and analyze text, images, audio, and video
  - Enable cross-modal synthesis and contextual understanding
- Tools:
  - Multimodal processing frameworks
  - Image/audio/video analytics libraries (OCR, CV modules)

### 8) Memory / Context Agents
- Capabilities:
  - Capture, organize, and recall information over long sessions
  - Manage persistent short/long-term memory for coherent reasoning
- Tools:
  - External memory stores (vector DBs, case banks, structured repos)
  - Contextual compression and retrieval algorithms
  - Knowledge graph and semantic web tools

## Implementing With PydanticAI

- Key capabilities:
  - Agent abstraction with typed inputs/outputs via Pydantic models
  - Type-safe tools/functions the agent can call during runs aka as functions???
  - Multi-turn runs with state and validated intermediate artifacts
  - Multi-agent composition (manager/worker) via validated messages. coordinator agent is manager, code interpreter agent is example of worker agent
  - Deterministic, parseable I/O for reliable orchestration
  - Observability hooks for tool calls and steps. aka adding logging

- Mapping to agent types:
  - Planner:
    - Define a PlannerAgent with a schema for a “Plan” (tasks, dependencies, acceptance criteria).
    - Tools: “create_subtasks”, “route_to_agent(agent_name, payload)”, “replan(on_result)”.
    - The planner produces a typed Plan; it invokes workers via tool calls that call sub-agents.

  - Execution specialists: per-domain agents with `TaskSpec` → `TaskResult`\
    - Define one agent per specialization (retrieval, synthesis, analysis, coding).
    - Inputs: a “TaskSpec” model; Outputs: “TaskResult”.
    - Tools limited to their domain (e.g., run_code, parse_pdf, summarize_docs).
  - Tool Caller/Invoker: shared typed tool registry (search, APIs, browser)
    - This can be a thin agent or just a tool registry the planner and workers share.
    - Register tools like: web_search(query), fetch_url(url), call_api(name, params).

  - Retrieval/Browser: browsing agent, uses web search tool
  - Analytics: returns uses code interpreter, outputs tables, charts, stats insights from structured data with other tools.
  - Code Interpreter: runs sandboxed code, primarily code only
  - Multimodal: OCR/ASR/caption tools returning `MultimodalFinding`
  - Memory/Context: `put_memory`, `get_memory`, `recall_chain` over your store

- Suggested structure:
    - one directory per agent

- Example tools (signatures):
  - `search_api(query: str, k: int) -> list[Document]`
  - `fetch_url(url: HttpUrl) -> str`
  - `run_python(code: str, inputs: dict) -> ExecutionResult`

- Multi-agent orchestration:
  - Planner produces `Plan` and delegates via `route_to_agent`
  - Sub-agents execute and return validated `TaskResult`
  - Planner checks acceptance criteria; calls `replan` if unmet
  - Synthesis assembles final report; Memory stores artifacts for recall

- Notes:
  - Strong typing ensures reliable cross-agent contracts
  - Tools are regular Python functions with Pydantic types
  - Long-running clients (browser/vector DB) live inside tools; I/O stays typed
  - Add logging/telemetry around tool calls for tracing
