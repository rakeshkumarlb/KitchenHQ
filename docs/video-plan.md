# KitchenHQ — Video Plan

Two videos, two audiences, one recurring cast of characters. Everything about
the videos — concept, script beats, shot list, and production notes — lives
here. Nothing in this file is code documentation; see `README.md` and
`CLAUDE.md` for that.

---

## The core creative idea

KitchenHQ already models a real restaurant's **kitchen brigade** — a chain of
command where each station has a name, a lane, and someone checking their
work. That's not a metaphor you have to invent for the video; it's already
true of the code (`CLAUDE.md`'s "The agents" section, `agents/prompts/*.md`).
Lean on it hard in both videos:

| Character | Real kitchen role it echoes | What it actually does | Existing icon (Sidebar/UI) |
|---|---|---|---|
| **The Executive Chef** | Head chef | Plans the week's menu, talks to you in chat, owns the recipe catalog | `Soup` |
| **The Sous Chef** | Second-in-command | Turns the menu into timed prep and cooking checklists | `ClipboardCheck` |
| **The Pantry Manager** | Kitchen steward | Watches stock, drafts the shopping list | `Package` |
| **The Food Inspector** | Health inspector | Grades the other three's work, out loud, in writing | `ShieldCheck` |

This casting is the single best "exciting" lever available: it turns an
otherwise dry "multi-agent orchestration" pitch into a **team with a hierarchy
and a built-in checks-and-balances joke** ("even the AI has an inspector
checking its homework"). Use the same four icons/colors as on-screen lower
thirds in *both* videos — viewers who watch both will recognize the cast
immediately, and it's zero extra design work since the app already draws them
that way.

**Suggested color key** (reuse in lower-thirds, captions, thumbnail):
- Executive Chef — warm amber/orange (menu, "Soup")
- Sous Chef — teal/green (tasks, "ClipboardCheck")
- Pantry Manager — blue (pantry, "Package")
- Food Inspector — red/crimson (audit, "ShieldCheck")

---

## Video 1 — General audience

**Working title:** *"I Hired an AI Kitchen Brigade to Run My House"*
(alt: *"Meet the AI Team That Plans My Family's Meals"*)

**Length:** 3–5 minutes. This audience does not know what an "agent" or
"MCP" is and does not need to. Zero jargon on screen or in narration —
if a word wouldn't survive being said to a parent at dinner, cut it.

**Goal:** make a non-technical viewer feel the *relief* of not having to
think about "what's for dinner" ever again, and plant the idea that a team
of specialized AIs (not one monolithic chatbot) can run a real recurring
household chore end-to-end, unsupervised, safely.

### Structure

**0:00–0:15 — Cold open, the pain.**
Handheld phone-camera energy, not polished. A tired parent staring into an
open fridge. Voiceover: *"What's for dinner?"* — the most-asked, least-loved
question in every house. Quick-cut through a week of chaos: forgotten
groceries, the same three meals on repeat, a shopping list scrawled on a
receipt.

**0:15–0:35 — The turn / hook.**
Cut to calm. *"So I built a kitchen staff that never sleeps."* Introduce the
concept in one line: not one AI, a **team** — like a real restaurant kitchen.
Cut to a fast, stylized "team lineup" — four character cards sliding in one
at a time (think heist-movie crew intro or a sports-team starting lineup),
each with its icon, a one-line job title, and a sting sound:
- "The Executive Chef — plans the week"
- "The Sous Chef — preps every meal"
- "The Pantry Manager — never lets you run out"
- "The Food Inspector — checks everyone's work"

**0:35–2:30 — A day in the life (the demo, disguised as a story).**
Narrate across one compressed "week" using a calendar/clock motif to show
time passing while the person lives their life:
1. *Saturday morning:* an email notification appears — "Your week's menu is
   ready." Cut to the **Weekly Menu** page scrolling past a full colorful
   grid of real dishes, macros, descriptions.
2. *That evening:* a phone buzzes — tonight's prep task. Cut to **Task
   List**, check a box, watch the **Pantry** quantity visibly drop in the
   same beat (this is the "wow, it's not just a to-do app" moment — the
   system *knows* what got used).
3. *Midweek:* stock for an item drops low — cut to the **Pantry Manager**
   quietly building a shopping list, no human involved, then the household
   member glancing at their phone and seeing it already done.
4. *A human moment:* someone types into **Chat** — "swap Tuesday's dinner,
   I'm tired of paneer" — and the Executive Chef responds conversationally
   and updates the plan live on screen.
5. *The twist that builds trust:* cut to the **Food Inspector** stamping a
   score/feedback badge onto the week's plan — frame it like a report card
   or a restaurant health-inspection grade sticker in a window. Narrate:
   *"And because I don't blindly trust one AI's judgment, a second one
   checks its work every night — and tells me exactly what it got wrong."*
   This single beat is what separates this from "yet another AI demo" —
   it shows a safety net, which is exactly what a skeptical non-technical
   viewer needs to see to trust automation with something as personal as
   feeding their family.

**2:30–3:10 — Payoff.**
Cut back to the family — but this time at the table, eating, relaxed,
no phones. Voiceover lands the emotional point: *"I didn't get less involved
in feeding my family. I got less involved in the part that was never the
fun part."* Show the freed-up time doing something else (a walk, homework
help, anything human).

**3:10–end — CTA.**
*"It's free, it's open source, and it runs entirely on your own computer —
your data never leaves your house."* Simple on-screen text: repo link,
"self-hosted," "your OpenAI key or a free local model." One line pointing
technical viewers at video 2: *"Curious how it's built? There's a second
video for that."*

### Shot list / assets needed
- Real kitchen b-roll (fridge, chopping, table) — can be stock footage if no time to film.
- Screen recordings: Dashboard → Weekly Menu → Task List (checking a box,
  showing the Pantry number change right after) → Pantry Manager's shopping
  list appearing → Chat exchange → a score/feedback badge close-up.
- Email notification screenshot/mockup (phone frame).
- Four character-card graphics (simple: icon + name + one-liner on a solid
  brand color card).
- A "week calendar" motif graphic to show time compressing.

### What would make this *more* exciting (pick 2–3, don't do all)
- **Voice each agent differently.** Even just a distinct notification sound
  per agent (a different chime for "menu ready" vs "shopping list ready" vs
  "audit complete") trains the viewer to recognize the cast by ear.
- **Cold open with a "before" testimonial** — a real complaint from your own
  life ("I ordered takeout four times last week because I hadn't planned")
  said straight to camera. Specific and personal beats generic narration.
- **Treat the Food Inspector as comic relief.** A deadpan "score: 62/100,
  needs more vegetables" is funny precisely because it's an AI being blunt
  about another AI's cooking choices. Consider giving it the most personality
  of the four in the edit (sound, pacing, a beat of comic timing).
- **End on a blooper.** Show one real moment where the system caught its own
  mistake — e.g., a menu run that fell short of a full week and got a
  corrective nudge, or a restriction that got flagged and fixed by the
  Inspector. "It's not perfect, and that's the point — nothing here happens
  without a check" is a stronger trust signal than pretending it's flawless.
- **Subtitle everything, always on.** This audience watches with sound off
  more often than not.

---

## Video 2 — Developers & enthusiasts

**Working title:** *"Building an AI Kitchen Brigade: Architecture, MCP, and
the Incident That Changed the Design"*

**Length:** 12–18 minutes, chaptered (YouTube chapters / timestamps in the
description). This audience wants real code, real diagrams, and real
tradeoffs — including the ones that didn't work.

**Goal:** teach transferable patterns (MCP dual-exposure, bounded connection
lifetimes, LLM-as-judge auditing, prompt-layer separation, hybrid search in
plain SQLite) through a real, running project — not a toy example. Establish
credibility by being honest about what's still prototype-grade.

### Structure

**0:00–0:30 — Cold open: the 30-second version of video 1.**
Rapid-fire cut of the same demo beats (menu → prep → pantry → audit) with a
single line: *"That's the outcome. Let's open the hood."* This hooks viewers
who land here without having seen video 1, and immediately signals "yes,
this is the technical one."

**0:30–2:00 — Chapter 1: Three services, one job each.**
Draw (or animate) the architecture diagram live: `dbmcp` (owns the SQLite DB,
exposes everything twice — REST *and* MCP, from one FastAPI app),
`agent-api` (the only process that talks to an LLM), `chatui` (a pure REST
client, no LangChain dependency at all). Emphasize *why* three services and
not one monolith: **each one can be redeployed, restarted, or replaced
independently** — the UI never needs to know an LLM exists.

**2:00–4:30 — Chapter 2: The MCP trick — one function, two doors.**
Live code walkthrough: a single `@tool`-decorated function in
`dbmcp/kitchendb/tools/*.py`, and show it being picked up *both* by
`build_mcp()` (→ an agent tool) *and* by a thin Pydantic REST route in
`routes.py` (→ what the React UI calls). The payoff line: **"The agent and
the human literally cannot see different data, because they call the same
function."** This is the single most reusable idea in the whole video for a
developer audience — show the two call sites side by side on screen.

**4:30–7:00 — Chapter 3: The war story — why nothing outlives one request.**
This is the strongest "developer trust" beat in the whole plan — lead with
it like a postmortem, because devs love postmortems:
> *"Early on, I built one LLM client per agent role and kept it alive for
> the life of the container. It worked — for a few days. Then a long-lived
> connection to my local Ollama server went stale and wedged it badly enough
> that other things on my machine couldn't reach Ollama either."*

Show the fix: `agents/app/kitchen_agent.run_agent()` builds a **fresh** LLM
client and MCP toolset per call, and disposes them in a `finally` block —
zero shared state, zero cross-call lock. Land the generalizable rule:
*"Every connection this codebase opens now has a lifetime of exactly one
request or one scheduled job. If you're building an agent that runs for
more than a demo, this is the bug you haven't hit yet."*

**7:00–9:00 — Chapter 4: Division of labor in prompts.**
Show `agents/prompts/system.md` (shared household context, no identity) vs.
`executive_chef.md`/`sous_chef.md`/etc. (standing behavior only) vs.
`agents/app/jobs.py`'s `SCHEDULED_REQUESTS` (the job-specific "which day,
which meals, which email, what's the time cap" detail). Explain the rule
that keeps this from rotting: *job-specific detail never leaks into the
role prompt.* All four roles share the exact same MCP toolset — lanes are
enforced by the prompt, not by hiding tools — mention this was a deliberate
simplification over an earlier per-role tool allowlist.

**9:00–11:30 — Chapter 5: The Food Inspector — LLM-as-judge as a pattern.**
This is the most novel architectural idea in the project and deserves its
own chapter, not a footnote:
- The old approach: a deterministic policy checker (`validate_weekly_menu_policy`,
  hardcoded restricted-term lists) that had to be kept in sync by hand.
- The new approach: `user_profile.restrictions` is fully household-editable,
  and a fourth agent role — one that **never plans anything** — scores every
  saved decision against those live rules and writes down *why*.
- Show the schema-level mechanism: `score`/`audit_feedback` columns, `NULL`
  = unaudited, four `get_unaudited_*`/`record_*_audit` MCP tool pairs, four
  nightly cron jobs.
- Name the accepted tradeoff on camera — this is a credibility move, not a
  weakness to hide: a non-compliant plan can reach the household and get
  acted on the same day, and is only caught after the fact via score/feedback.
  *"I chose one rule source over a second, duplicated deterministic gate
  that would drift the moment restrictions became configurable."*
- Show the live UI payoff: the Recipes page's "refresh tags" button feeding
  the Food Inspector's own last feedback back into the Executive Chef's next
  rewrite — a closed loop from audit → fix, one click, on screen.

**11:30–13:30 — Chapter 6: A recipe catalog with a vector search column and no vector database.**
Show `dbmcp/kitchendb/tools/recipes.py`: one SQLite row holds the structured
recipe, its embedding, and its rating together, so the row and its search
vector can never drift apart. Show `search_recipes` blending keyword scoring
(`keyword_search.py`) and cosine similarity (`embeddings.py`) — a recipe
surfaces if *either* clears the match threshold. The pitch to developers:
*"You don't need Pinecone for a project this size — you need one extra
column."*

**13:30–15:30 — Chapter 7: Scheduling and observability.**
Show `agents/app/scheduler.py`'s in-process `AsyncIOScheduler` (11 jobs, no
extra worker container), then a live click of "Run now" on the
**Automations** page, then a quick look at the **Usage Stats** page —
token/context usage per agent role, so cost is visible, not a surprise
invoice. Mention the "shortfall → nudge → raise, never a blank success"
guardrail (`run_agent`'s `require_tools`/`require_tool_counts`) as the thing
that makes `agent_runs.status` trustworthy.

**15:30–17:00 — Chapter 8: What's still prototype-grade, and what's next.**
Be honest on camera: one shared API key (no per-user accounts), SQLite with
no replication, no CI, no tests outside `dbmcp`. This isn't a weakness to
hide from a developer audience — it's what makes the rest of the video
credible. End with an invitation: link to the repo, "open an issue, send a
PR, or just fork it for your own kitchen."

**17:00–end — Outro.**
Tech stack recap card (Python/FastAPI/FastMCP/LangChain/APScheduler/SQLite,
React/Vite), repo link, "the general-audience video is linked if you want
to send this to someone who doesn't care about any of the above."

### Shot list / assets needed
- Animated or hand-drawn architecture diagram (reuse/upgrade the ASCII one
  in `README.md`).
- Side-by-side code view: the `@tool` function + its MCP registration + its
  REST route, all three visible at once.
- A simple before/after diagram for the connection-lifetime incident
  (long-lived client vs. fresh-per-request).
- Schema screenshot or diagram: `score`/`audit_feedback` columns highlighted
  across `weekly_menu`, `weekly_plans`, `detailed_prep_schedule`, `recipes`.
- Live terminal: `docker compose up --build`, then a live `/invoke/{job}`
  call via the Automations page.
- Usage Stats page screen recording.

### What would make this *more* exciting (pick 2–3, don't do all)
- **Lead with the incident, not the architecture.** Postmortems are the most
  addictive content format for developers — consider opening chapter order
  with the war story right after the 30-second recap, then backfilling the
  architecture as "here's the system that story happens inside."
  This restructure trades a cleaner build-up for a stronger hook — a real
  editorial choice, not just a nice-to-have; make it deliberately.
  Recommended default: try it, only revert to architecture-first if it tests worse.
- **Show a failing run on screen, live.** Trigger a job, deliberately show
  the `require_tool_counts` shortfall path firing a corrective nudge in the
  logs. Developers trust systems more when they see the failure path work,
  not just the happy path.
- **Diff-based storytelling.** For the "old deterministic checker → Food
  Inspector" story and the "one LLM client per role → fresh per request"
  story, show an actual `git log`/`git show` of the real commit that made
  the change, not a reconstruction. It's more credible and it's free —
  the history already exists.
- **Chapter markers matching this file's headers exactly**, so viewers can
  jump straight to "the MCP trick" or "the war story" — this is a discovery
  and rewatch lever, not just organization.

---

## Shared production notes

- **Recording:** screen-record at 1440p+ regardless of final export
  resolution — code and small UI text need the headroom.
- **Consistency between videos:** same four agent icons/colors, same theme
  music family (a calmer variant for video 2), same repo link card style.
- **Thumbnails:**
  - Video 1: the four character cards, bold text like "I gave my kitchen a
    staff."
  - Video 2: the architecture diagram with one line crossed out/rewritten
    (visually signals "real engineering story," not just a tutorial).
- **Titles for search:** video 1 should surface for "AI home automation" /
  "AI meal planning" searches; video 2 should surface for "multi-agent",
  "MCP", "LangChain agent architecture", "LLM as judge" searches — use those
  terms in the video 2 description even if not spoken on camera.
- **Publish order:** video 1 first (wider funnel), with a pinned comment /
  end-card linking video 2 for anyone who says "how does this actually
  work?" in the comments — that question is guaranteed to show up.
