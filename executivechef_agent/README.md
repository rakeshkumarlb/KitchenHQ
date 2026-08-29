# KitchenHQ Executive Chef Agent

This is a standalone LangChain agent that uses the KitchenHQ database through the MCP server. It keeps an interactive terminal conversation open while APScheduler runs the weekly menu and recurring prep workflows in the same process.

## Run with Docker

Copy `executivechef_agent/.env.example` to `executivechef_agent/.env`, set `OPENAI_API_KEY` and `KITCHENHQ_API_KEY` (must match the `dbmcp` service's key), then start both services from the repository root:

```powershell
docker compose up --build
```

The agent container is interactive. Type requests such as `show me low-stock ingredients` or `create a random recipe`, and type `quit` to stop it. The database MCP endpoint remains available at `http://localhost:18000/mcp`.

## Run the agent locally

Start the existing `dbmcp` container, set `MCP_URL=http://localhost:18000/mcp` and `KITCHENHQ_API_KEY`, install `executivechef_agent/requirements.txt`, and run:

```powershell
python executivechef_agent/agent.py
```

Set `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL` to use Ollama instead of OpenAI.