import os
import sqlite3
import threading
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI 
from langchain_core.messages import SystemMessage
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import prompts

load_dotenv(".env", override=False)
load_dotenv(".env.local", override=False)

# 1. Setup Database & LLM
db = SQLDatabase.from_uri("sqlite:///kitchen.db")
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=os.environ.get("OPEN_API_KEY"),
)

# 2. Setup Slack App
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
SLACK_CHANNEL = "#kitchen-management"

def get_agent(prompt_text):
    return create_sql_agent(
        llm, 
        db=db, 
        agent_type="openai-tools", 
        verbose=False,
        messages=[SystemMessage(content=prompt_text)]
    )

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
        "morning": "Generate today's 20-minute parallel morning execution plan. Log it in task_acknowledgement."
    }
    
    plan = sous_chef.invoke({"input": prompt_map[task_type]})
    
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
        trigger_sous_chef("morning")

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

    print("Connecting to Slack via Socket Mode...")
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()