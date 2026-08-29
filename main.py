import os
import asyncio
import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path
from threading import Lock
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from slack_bolt import App

try:
    from langchain_ollama import ChatOllama
except ImportError:
    from langchain_community.chat_models import ChatOllama
from slack_bolt.adapter.socket_mode import SocketModeHandler
from langchain_mcp_adapters.client import MultiServerMCPClient
import prompts

load_dotenv(".env", override=False)
load_dotenv(".env.local", override=False)

# 1. Setup LLM and MCP database tools
ollama_api_key = os.environ.get("OLLAMA_API_KEY")
if not ollama_api_key:
    raise RuntimeError("OLLAMA_API_KEY must be set to use Ollama Cloud")

llm = ChatOllama(
    model=os.environ.get("OLLAMA_MODEL", "gemma4"),
    temperature=0.3,
    base_url=os.environ.get("OLLAMA_BASE_URL", "https://ollama.com"),
    client_kwargs={
        #"headers": {"Authorization": f"Bearer {ollama_api_key}"},
    },
)

async def _load_mcp_tools():
    client = MultiServerMCPClient({
        "kitchenhq": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(Path(__file__).with_name("mcp_server.py"))],
        }
    })
    return await client.get_tools()

class _AsyncRunner:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        return future.result()


_async_runner = _AsyncRunner()

class McpAgent:
    """Keep the existing synchronous agent interface over async MCP tools."""

    def __init__(self, prompt_text):
        self.prompt_text = prompt_text

    @staticmethod
    def _text(message):
        content = message.content
        if isinstance(content, str):
            return content
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )

    def invoke(self, payload):
        input_text = payload["input"]
        result = _async_runner.run(self._ainvoke(input_text))
        final_message = result["messages"][-1]
        return {"output": self._text(final_message), "messages": result["messages"]}

    async def _ainvoke(self, input_text):
        mcp_tools = await _load_mcp_tools()
        agent = create_agent(
            model=llm,
            tools=mcp_tools,
            system_prompt=self.prompt_text,
        )
        return await agent.ainvoke({
            "messages": [{"role": "user", "content": input_text}]
        })


def _create_mcp_agent(prompt_text):
    return McpAgent(prompt_text)

# 2. Setup Slack App
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
SLACK_CHANNEL = "#kitchen-management"
conversation_histories = {}
conversation_histories_lock = Lock()

# create a conversational agent that can handle multi-turn conversations and maintain context
def get_conversational_agent():
    custom_suffix = """
    If you receive a data response from the previous tool-call,
    you MUST immediately stop and return that data as the final answer.
    DO NOT attempt to call any other tools or generate any other output.
    """

    return _create_mcp_agent(prompts.AGENT_3_SOUS_CHEF)
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_text),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    conversation = prompt | llm

    def get_session_history(session_id):
        with conversation_histories_lock:
            if session_id not in conversation_histories:
                conversation_histories[session_id] = InMemoryChatMessageHistory()
            return conversation_histories[session_id]

    return RunnableWithMessageHistory(
        conversation,
        get_session_history,
        input_messages_key="input",
        history_messages_key="history",
    )"""


def get_agent(prompt_text):
    return _create_mcp_agent(prompt_text)

# --- SLACK OUTBOUND (THE SCHEDULER) ---
def weekly_retrospective_and_grocery():
    # Ping the family on Friday
    app.client.chat_postMessage(
        channel=SLACK_CHANNEL, 
        text="👋 *Friday Kitchen Retro!* How did the kids rate this week's lunches (1-5)? Did we waste any veggies? (Reply starting with 'Feedback:')"
    )
    # The actual grocery generation happens after the human replies (handled in SLACK INBOUND).

def generate_weekly_menu():
    app.client.chat_postMessage(channel=SLACK_CHANNEL, text="⏳ Generating next week's menu...")
    chef_agent = get_agent(prompts.AGENT_2_CHEF)
    menu = chef_agent.invoke({"input": "Generate next week's macro-balanced Mon-Fri menu. Write it to the database."})
    
    app.client.chat_postMessage(
        channel=SLACK_CHANNEL, 
        text=f"🍽️ *Next Week's Menu is Ready:*\n{menu['output']}"
    )

def trigger_sous_chef(task_type):
    print(f"Triggering Sous-Chef for {task_type} prep...")
    sous_chef = get_agent(prompts.AGENT_3_SOUS_CHEF)
    prompt_map = {
        "sunday": "Generate the 60-minute Sunday batch-prep plan.",
        "nightly": "Generate tonight's 3-minute prep for tomorrow's menu. Log it in task_acknowledgement.",
        "morning": "Generate today's 20-minute parallel morning execution plan.",
        "random": "Generate a random recipe based on available ingredients."
    }
    
    plan = sous_chef.invoke({"input": prompt_map[task_type]})

    print(f"Generated Sous-Chef plan for {task_type}: {plan}")
    app.client.chat_postMessage(
        channel=SLACK_CHANNEL, 
        text=f"🔪 *Sous-Chef Action Required [{task_type.upper()}]:*\n\n{plan['output']}\n\n_Reply with 'DONE' or 'SKIPPED [reason]'_"
    )

# --- SLACK INBOUND (THE LISTENER) ---

@app.message("(?i)^(done|skipped).*")
def handle_task_acknowledgement(message, say):
    """Catches replies starting with DONE or SKIPPED"""
    human_text = message['text']
    say(f"Got it! Updating the kitchen logs... 📝")
    
    sous_chef = get_agent(prompts.AGENT_3_SOUS_CHEF)
    sous_chef.invoke({"input": f"The human replied '{human_text}'. Update the task_acknowledgement table."})
    say("✅ Task log updated.")

@app.message("(?i)^feedback:.*")
def handle_friday_feedback(message, say):
    """Catches Friday feedback and triggers the grocery generation"""
    human_text = message['text']
    say("Processing feedback and generating the new grocery list... 🛒")
    
    # Update DB with feedback
    inventory_agent = get_agent(prompts.AGENT_1_INVENTORY)
    inventory_agent.invoke({"input": f"Log this feedback: {human_text}"})
    
    # Generate Report & Groceries
    chef_agent = get_agent(prompts.AGENT_2_CHEF)
    report = chef_agent.invoke({"input": "Generate the Weekly Retrospective Report based on recent feedback, then generate next week's grocery list taking wastage into account."})
    
    say(f"📊 *Weekly Report & Groceries:*\n{report['output']}")

# --- MULTI-THREADING RUNNER ---

@app.event("message")
def handle_message_events(event, say):
    """Catch all messages and route to appropriate handlers"""
    text = event.get('text', '')
    print(f"Received message: {text}")
    if text.lower().startswith("feedback:"):
        handle_friday_feedback(event, say)
    elif text.lower().startswith("done") or text.lower().startswith("skipped"):
        handle_task_acknowledgement(event, say)
    elif "sous-chef" in text.lower():
        print("Triggered Sous-Chef for morning prep.")
        handle_conversational_sous_chef(event, say)

def handle_conversational_sous_chef(message, say):
    sous_chef = get_conversational_agent()
    # loop until exit is typed
    session_id = message.get("user") or message.get("channel", "default")
    response = sous_chef.invoke({"input": message.get("text", "")})
    say(response["output"])

def run_scheduler():
    scheduler = BlockingScheduler()
    scheduler.add_job(weekly_retrospective_and_grocery, 'cron', day_of_week='fri', hour=17, minute=0)
    scheduler.add_job(generate_weekly_menu, 'cron', day_of_week='sat', hour=10, minute=0)
    scheduler.add_job(lambda: trigger_sous_chef("sunday"), 'cron', day_of_week='sun', hour=14, minute=0)
    scheduler.add_job(lambda: trigger_sous_chef("nightly"), 'cron', day_of_week='sun-thu', hour=20, minute=0)
    scheduler.add_job(lambda: trigger_sous_chef("morning"), 'cron', day_of_week='mon-fri', hour=6, minute=30)
    scheduler.start()

if __name__ == "__main__":
    #print("Starting APScheduler in background thread...")
    #scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    #scheduler_thread.start()

    #print("Connecting to Slack via Socket Mode...")
    #SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
    #sous_chef.run({"input": "Create some random ingredients for this week."})
    #sous_chef.run({"input": "Create a weekly menu for this week and update the database"})
    #sous_chef.run({"input": "Create a 60-minute Sunday batch-prep plan for this week's menu and update the database"})
    while True:
        sous_chef = get_conversational_agent()
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("Exiting...")
            break
        response = sous_chef.invoke({"input": user_input})
        print(f"Sous-Chef: {response}")

    