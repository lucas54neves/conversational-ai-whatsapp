# Design: Agente de Saúde e Nutrição no WhatsApp

**Data:** 2026-04-29
**Domínio:** Nutrição e acompanhamento de macros
**Canal:** WhatsApp via Omni (Baileys)
**Orquestrador:** Genie (Claude Code nativo)

---

## 1. Visão Geral

Agente conversacional que permite ao usuário registrar refeições em linguagem natural, acompanhar calorias e macros (proteína, carboidrato, gordura) e consultar histórico semanal. As metas diárias são calculadas automaticamente via fórmula Mifflin-St Jeor com base no perfil do usuário.

O diferencial em relação a outros candidatos: uso da **TACO (Tabela Brasileira de Composição de Alimentos)** como base de dados nutricional local — sem dependência de APIs externas em runtime, com cobertura de alimentos tipicamente brasileiros (feijão, arroz, farofa, tapioca, etc.).

---

## 2. Arquitetura Geral

```
Usuário WhatsApp
      │
      ▼
   Omni (Baileys)          ← bridge WhatsApp
      │
      ▼
   Genie Agent             ← orquestrador de sessão e contexto
      │
      ▼
  Claude Code              ← interpreta linguagem natural, decide ferramentas
      │
  ┌───┴────────────────┐
  ▼                    ▼
MCP Server          PostgreSQL
(nutrition-tools)   ┌─────────────┐
  │                 │ taco_foods  │  ← ~600 alimentos brasileiros (TACO)
  │                 │ users       │  ← perfil + metas calculadas
  └──────────────►  │ meal_logs   │  ← histórico de refeições
                    └─────────────┘
```

### Camadas

| Camada | Componente | Responsabilidade |
|--------|-----------|-----------------|
| Canal | Omni | Recebe e envia mensagens no WhatsApp via Baileys |
| Orquestração | Genie | Mantém sessão por `phone_number`, preserva contexto da conversa |
| Inteligência | Claude Code | Interpreta texto livre, escolhe ferramentas, confirma com usuário |
| Capacidades | MCP Server `nutrition-tools` | Busca alimentos, salva refeições, retorna resumos |
| Persistência | PostgreSQL | TACO + perfis de usuários + logs de refeições |

---

## 3. Schema do Banco de Dados

```sql
-- Alimentos da TACO (~600 itens típicos brasileiros)
CREATE TABLE taco_foods (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    calories    NUMERIC(7,2),  -- kcal por 100g
    protein     NUMERIC(6,2),  -- g por 100g
    carbs       NUMERIC(6,2),  -- g por 100g
    fat         NUMERIC(6,2)   -- g por 100g
);
CREATE INDEX ON taco_foods USING GIN (to_tsvector('portuguese', name));

-- Perfil e metas calculadas por usuário
CREATE TABLE users (
    phone_number    TEXT PRIMARY KEY,  -- identificador do WhatsApp
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

-- Log de refeições
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

### Decisões de design

- `phone_number` como chave primária de `users`: o WhatsApp já provê identificação única via Omni, sem autenticação adicional.
- Índice GIN full-text em português na TACO: permite busca fuzzy por nome de alimento sem dependência de extensões extras.
- Metas salvas desnormalizadas em `users`: evita recalcular Mifflin-St Jeor a cada mensagem.

---

## 4. Ferramentas do Agente (MCP Server `nutrition-tools`)

### `search_food(query: str) → list[FoodResult]`
Busca na tabela `taco_foods` por full-text search em português. Retorna até 5 candidatos com nome e macros por 100g. Claude usa o resultado com maior relevância sem perguntar ao usuário; se houver ambiguidade semântica real (ex: "arroz branco" vs "arroz integral"), lista as opções numeradas e pede escolha antes de chamar `save_meal`.

### `save_user_profile(phone, weight_kg, height_cm, age, sex, goal) → UserProfile`
Salva perfil, calcula metas via Mifflin-St Jeor com fator de atividade sedentário e ajuste por objetivo:
- `lose`: −300 kcal
- `maintain`: sem ajuste
- `gain`: +300 kcal

### `get_user_profile(phone) → UserProfile | None`
Retorna perfil e metas. Retorno `None` aciona onboarding.

### `save_meal(phone, food_name, taco_food_id, quantity_g) → MealLog`
Calcula calorias e macros proporcionais à quantidade e insere em `meal_logs`.

### `get_daily_summary(phone, date?: str) → DailySummary`
Agrega `meal_logs` do dia. Retorna total consumido, meta e percentual de cada macro.

### `get_weekly_history(phone) → list[DailySummary]`
Retorna os últimos 7 dias com total diário de calorias e macros.

---

## 5. Fluxos Principais

### Onboarding (primeiro acesso)
```
Usuário: qualquer mensagem
Claude:  detecta ausência de perfil via get_user_profile
Claude:  "Olá! Vou precisar do seu perfil para calcular suas metas.
          Qual é o seu peso em kg?"
Usuário: "78"
Claude:  "Sua altura em cm?"
...      [coleta peso, altura, idade, sexo, objetivo]
Claude:  save_user_profile(...)
Claude:  "Suas metas diárias: 2.100 kcal | 157g proteína |
          263g carboidrato | 70g gordura."
```

### Registro de refeição
```
Usuário: "almocei 200g de frango grelhado e 150g de arroz"
Claude:  search_food("frango grelhado") → Frango grelhado: 219 kcal/100g
Claude:  search_food("arroz") → Arroz branco cozido: 128 kcal/100g
Claude:  "Entendi:
          • Frango grelhado (200g): 438 kcal | 42g prot | 0g carbo | 10g gord
          • Arroz branco cozido (150g): 192 kcal | 3g prot | 42g carbo | 0g gord
          Total: 630 kcal. Confirmar?"
Usuário: "sim"
Claude:  save_meal(frango, 200g) + save_meal(arroz, 150g)
Claude:  "Registrado. Hoje: 1.240 kcal / 2.100 kcal (59%).
          Proteína: 98g / 157g."
```

### Consulta de progresso
```
Usuário: "como estou hoje?"
Claude:  get_user_profile(phone) + get_daily_summary(phone)
Claude:  "Hoje (29/04):
          Calorias: 1.240 / 2.100 kcal (59%)
          Proteína: 98 / 157g (62%)
          Carboidrato: 142 / 263g (54%)
          Gordura: 38 / 70g (54%)"
```

### Histórico semanal
```
Usuário: "me mostra minha semana"
Claude:  get_weekly_history(phone)
Claude:  "Últimos 7 dias:
          23/04 — 1.890 kcal ✓
          24/04 — 2.340 kcal ▲
          ...
          29/04 — 1.240 kcal (em andamento)"
```

---

## 6. Tratamento de Erros e Edge Cases

| Situação | Comportamento |
|----------|--------------|
| Usuário sem perfil | Onboarding obrigatório antes de aceitar qualquer registro |
| Alimento não encontrado na TACO | Claude informa e pede reformulação ou valores manuais |
| Quantidade ausente na mensagem | Claude pergunta antes de chamar `save_meal` |
| Múltiplos candidatos ambíguos | Claude lista opções numeradas e pede escolha |
| Usuário cancela confirmação | Descarta sem salvar, pergunta o que corrigir |
| Mensagem fora do domínio | Claude responde brevemente e sugere o que pode fazer |
| Dados de perfil inválidos | Rejeita valores fora de faixas fisiológicas razoáveis |

---

## 7. Estrutura do Projeto

```
conversational-ai-whatsapp/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── agent/
│   └── CLAUDE.md                 ← system prompt + instruções do agente
│
├── mcp-server/
│   ├── pyproject.toml
│   ├── src/
│   │   └── nutrition_tools/
│   │       ├── server.py         ← entrypoint MCP
│   │       ├── tools.py          ← implementação das 6 ferramentas
│   │       ├── db.py             ← conexão PostgreSQL
│   │       └── calculator.py     ← fórmula Mifflin-St Jeor
│   └── Dockerfile
│
└── db/
    ├── migrations/
    │   └── 001_init.sql          ← schema das 3 tabelas
    └── seed/
        ├── taco.csv              ← dados TACO
        └── seed.py               ← script de importação
```

---

## 8. Infraestrutura

### Serviços no host (instaladores oficiais)

Genie e Omni não publicam imagens Docker — são instalados diretamente no host:

```bash
# Genie (binário verificado via cosign + SLSA)
curl -fsSL https://get.automagik.dev/genie | bash

# Omni (Node.js/Bun, gerencia PostgreSQL + NATS via PM2)
bun add -g @automagik/omni
omni install
```

Omni sobe seu próprio PostgreSQL (porta 8432), NATS (porta 4222) e API (porta 8882) via PM2.

### Docker Compose (apenas nossos serviços)

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

### Variáveis de ambiente (`.env`)

```
ANTHROPIC_API_KEY=
POSTGRES_PASSWORD=
MCP_SERVER_URL=http://localhost:8000   # usado na config do Genie
```

### Setup completo

```bash
# 1. Instalar Genie e Omni no host
curl -fsSL https://get.automagik.dev/genie | bash
bun add -g @automagik/omni && omni install

# 2. Subir nossos serviços (PostgreSQL + seed + MCP server)
cp .env.example .env        # preencher ANTHROPIC_API_KEY e POSTGRES_PASSWORD
docker compose up seed      # importa TACO (roda uma vez)
docker compose up -d mcp-server postgres

# 3. Configurar Genie para usar o MCP server e iniciar
# (configuração via agent/CLAUDE.md + variáveis de ambiente)
genie start

# 4. Conectar Omni ao Genie
omni config set agent_url http://localhost:<genie_port>
omni start
```

---

## 9. Diferenciais Técnicos

- **TACO como fonte de dados**: cobertura de alimentos brasileiros sem chamadas externas em runtime
- **Identificação por `phone_number`**: zero fricção de autenticação para o usuário
- **Confirmação antes de salvar**: evita registros incorretos por ambiguidade de linguagem natural
- **Busca full-text em português**: índice GIN com dicionário `portuguese` para lidar com variações de nome
