# Design: Nutrition & Health Agent on WhatsApp

**Date:** 2026-04-29
**Domain:** Nutrition tracking and macro management
**Channel:** WhatsApp via Omni (Baileys)
**Orchestrator:** Genie (native Claude Code)

---

## 1. Overview

A conversational agent that allows users to log meals in natural language, track calories and macros (protein, carbohydrate, fat), and query their weekly history. Daily targets are automatically calculated via the Mifflin-St Jeor formula based on the user's profile.

Key differentiator: the **TACO (Brazilian Food Composition Table)** is imported as a local database — no runtime dependency on external nutrition APIs, with full coverage of typical Brazilian foods (feijão, arroz, farofa, tapioca, etc.).

---

## 2. Overall Architecture

```
WhatsApp User
      │
      ▼
   Omni (Baileys)          ← WhatsApp bridge
      │
      ▼
   Genie Agent             ← session and context orchestrator
      │
      ▼
  Claude Code              ← interprets natural language, decides tool calls
      │
  ┌───┴────────────────┐
  ▼                    ▼
MCP Server          PostgreSQL
(nutrition-tools)   ┌─────────────┐
  │                 │ taco_foods  │  ← ~600 Brazilian foods (TACO)
  │                 │ users       │  ← profile + calculated targets
  └──────────────►  │ meal_logs   │  ← meal history
                    └─────────────┘
```

### Layers

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| Channel | Omni | Receives and sends WhatsApp messages via Baileys |
| Orchestration | Genie | Maintains session per `phone_number`, preserves conversation context |
| Intelligence | Claude Code | Interprets free text, selects tools, confirms with user |
| Capabilities | MCP Server `nutrition-tools` | Searches foods, saves meals, returns summaries |
| Persistence | PostgreSQL | TACO data + user profiles + meal logs |

---

## 3. Database Schema

```sql
-- TACO foods (~600 typical Brazilian items)
CREATE TABLE taco_foods (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    calories    NUMERIC(7,2),  -- kcal per 100g
    protein     NUMERIC(6,2),  -- g per 100g
    carbs       NUMERIC(6,2),  -- g per 100g
    fat         NUMERIC(6,2)   -- g per 100g
);
CREATE INDEX ON taco_foods USING GIN (to_tsvector('portuguese', name));

-- User profile and calculated targets
CREATE TABLE users (
    phone_number    TEXT PRIMARY KEY,  -- WhatsApp identifier
    weight_kg       NUMERIC(5,2),
    height_cm       INT,
    age             INT,
    sex             TEXT CHECK (sex IN ('M', 'F')),
    goal            TEXT CHECK (goal IN ('lose', 'maintain', 'gain')),
    target_calories NUMERIC(7,2),
    target_protein  NUMERIC(6,2),
    target_carbs    NUMERIC(6,2),
    target_fat      NUMERIC(6,2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Meal log
CREATE TABLE meal_logs (
    id           SERIAL PRIMARY KEY,
    phone_number TEXT REFERENCES users(phone_number),
    food_name    TEXT NOT NULL,
    taco_food_id INT REFERENCES taco_foods(id),
    quantity_g   NUMERIC(6,1),
    calories     NUMERIC(7,2),
    protein      NUMERIC(6,2),
    carbs        NUMERIC(6,2),
    fat          NUMERIC(6,2),
    logged_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON meal_logs (phone_number, logged_at);
```

### Design decisions

- `phone_number` as primary key for `users`: WhatsApp already provides unique identification via Omni — no additional auth needed.
- GIN full-text index with Portuguese dictionary on `taco_foods`: enables fuzzy search by food name without extra extensions.
- Targets stored denormalized in `users`: avoids recalculating Mifflin-St Jeor on every message.

---

## 4. Agent Tools (MCP Server `nutrition-tools`)

### `search_food(query: str) → list[FoodResult]`
Full-text search on `taco_foods` using a Portuguese dictionary. Returns up to 5 candidates with name and macros per 100g. Claude selects the highest-relevance result without asking the user; if there is genuine semantic ambiguity (e.g., "white rice" vs "brown rice"), it lists numbered options and asks for a choice before calling `save_meal`.

### `save_user_profile(phone, weight_kg, height_cm, age, sex, goal) → UserProfile`
Saves the profile and calculates daily targets via Mifflin-St Jeor with a sedentary activity factor, adjusted by goal:
- `lose`: −300 kcal
- `maintain`: no adjustment
- `gain`: +300 kcal

### `get_user_profile(phone) → UserProfile | None`
Returns profile and targets. A `None` result triggers the onboarding flow.

### `save_meal(phone, food_name, taco_food_id, quantity_g) → MealLog`
Calculates calories and macros proportional to quantity and inserts into `meal_logs`.

### `get_daily_summary(phone, date?: str) → DailySummary`
Aggregates `meal_logs` for the day. Returns total consumed vs. target and percentage per macro.

### `get_weekly_history(phone) → list[DailySummary]`
Returns the last 7 days with daily totals for calories and macros.

---

## 5. Main Conversation Flows

### Onboarding (first access)
```
User:   any message
Claude: detects missing profile via get_user_profile → None
Claude: "Hi! I need your profile to calculate your daily targets.
         What is your weight in kg?"
User:   "78"
Claude: "Your height in cm?"
...     [collects weight, height, age, sex, goal]
Claude: save_user_profile(...)
Claude: "Your daily targets: 2,100 kcal | 157g protein |
         263g carbs | 70g fat."
```

### Meal logging
```
User:   "had 200g grilled chicken and 150g rice for lunch"
Claude: search_food("grilled chicken") → Frango grelhado: 219 kcal/100g
Claude: search_food("rice") → Arroz branco cozido: 128 kcal/100g
Claude: "Got it:
         • Grilled chicken (200g): 438 kcal | 42g protein | 0g carbs | 10g fat
         • White rice, cooked (150g): 192 kcal | 3g protein | 42g carbs | 0g fat
         Total: 630 kcal. Confirm?"
User:   "yes"
Claude: save_meal(chicken, 200g) + save_meal(rice, 150g)
Claude: "Logged. Today: 1,240 / 2,100 kcal (59%).
         Protein: 98 / 157g."
```

### Daily progress query
```
User:   "how am I doing today?"
Claude: get_user_profile(phone) + get_daily_summary(phone)
Claude: "Today (Apr 29):
         Calories: 1,240 / 2,100 kcal (59%)
         Protein:  98 / 157g (62%)
         Carbs:    142 / 263g (54%)
         Fat:      38 / 70g (54%)"
```

### Weekly history
```
User:   "show me my week"
Claude: get_weekly_history(phone)
Claude: "Last 7 days:
         Apr 23 — 1,890 kcal ✓
         Apr 24 — 2,340 kcal ▲
         ...
         Apr 29 — 1,240 kcal (in progress)"
```

---

## 6. Error Handling and Edge Cases

| Situation | Behavior |
|-----------|----------|
| User has no profile | Onboarding is mandatory before accepting any meal log |
| Food not found in TACO | Claude informs and asks for reformulation or manual values |
| Quantity missing from message | Claude asks before calling `save_meal` |
| Multiple ambiguous candidates | Claude lists numbered options and asks for a choice |
| User cancels confirmation | Discards without saving, asks what to correct |
| Out-of-domain message | Claude responds briefly and suggests what it can do |
| Invalid profile data | Rejects values outside physiologically reasonable ranges |

---

## 7. Project Structure

```
conversational-ai-whatsapp/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── agent/
│   └── CLAUDE.md                 ← system prompt + agent instructions
│
├── mcp-server/
│   ├── pyproject.toml
│   ├── src/
│   │   └── nutrition_tools/
│   │       ├── server.py         ← MCP entrypoint
│   │       ├── tools.py          ← 6 tool implementations
│   │       ├── db.py             ← PostgreSQL connection
│   │       └── calculator.py     ← Mifflin-St Jeor formula
│   └── Dockerfile
│
└── db/
    ├── migrations/
    │   └── 001_init.sql          ← 3-table schema
    └── seed/
        ├── taco.csv              ← TACO dataset
        └── seed.py               ← import script
```

---

## 8. Infrastructure

### Host services (official installers)

Genie and Omni do not publish Docker images — they are installed directly on the host:

```bash
# Genie (cosign + SLSA verified binary)
curl -fsSL https://get.automagik.dev/genie | bash

# Omni (Node.js/Bun, manages PostgreSQL + NATS via PM2)
bun add -g @automagik/omni
omni install
```

Omni starts its own PostgreSQL (port 8432), NATS (port 4222), and API (port 8882) via PM2.

### Docker Compose (our services only)

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: nutrition
      POSTGRES_USER: nutrition
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  seed:
    build: ./db/seed
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://nutrition:${POSTGRES_PASSWORD}@postgres:5432/nutrition

  mcp-server:
    build: ./mcp-server
    ports:
      - "8000:8000"
    depends_on: [postgres]
    environment:
      DATABASE_URL: postgresql://nutrition:${POSTGRES_PASSWORD}@postgres:5432/nutrition

volumes:
  postgres_data:
```

### Environment variables (`.env`)

```
ANTHROPIC_API_KEY=
POSTGRES_PASSWORD=
MCP_SERVER_URL=http://localhost:8000   # used in Genie config
```

### Full setup

```bash
# 1. Install Genie and Omni on the host
curl -fsSL https://get.automagik.dev/genie | bash
bun add -g @automagik/omni && omni install

# 2. Start our services (PostgreSQL + seed + MCP server)
cp .env.example .env        # fill in ANTHROPIC_API_KEY and POSTGRES_PASSWORD
docker compose up seed      # import TACO (runs once)
docker compose up -d mcp-server postgres

# 3. Configure Genie to use the MCP server and start
# (configured via agent/CLAUDE.md + environment variables)
genie start

# 4. Connect Omni to Genie
omni config set agent_url http://localhost:<genie_port>
omni start
```

---

## 9. Technical Differentiators

- **TACO as data source**: Brazilian food coverage with no runtime external API calls.
- **`phone_number` as primary key**: zero authentication friction for the user.
- **Confirmation before saving**: prevents incorrect logs from natural language ambiguity.
- **Portuguese full-text search**: GIN index with `portuguese` dictionary handles food name variations.
