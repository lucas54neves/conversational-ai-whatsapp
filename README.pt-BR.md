# Agente Conversacional de Nutrição no WhatsApp

[EN](README.md) - [PT](README.pt-BR.md)

Um assistente de nutrição em português brasileiro que roda no WhatsApp.
Os usuários registram refeições em linguagem natural e o agente acompanha
calorias e macros em relação às metas diárias calculadas a partir de um
perfil pessoal (Mifflin-St Jeor com fator de atividade sedentário,
ajustado pelo objetivo). Todos os dados de alimentos vêm de uma cópia
local da tabela brasileira de composição de alimentos TACO — sem APIs
externas de nutrição em tempo de execução.

O pipeline é:

```
WhatsApp ──► Omni (Baileys) ──► Genie (Claude Code) ──► servidor MCP ──► Postgres (TACO + registros de refeições)
```

## Arquitetura

O sistema é dividido em dois planos:

- **Plano de dados containerizado** — Postgres 16, um seeder one-shot que
  executa a migração do schema e carrega a tabela de alimentos TACO, e o
  servidor MCP em Python. Os três vivem em `docker-compose.yml`.
- **Plano de runtime no host** — Claude Code, Genie e Omni rodam como
  binários instalados no host porque não são distribuídos como imagens de
  contêiner. O Genie embute seu próprio Postgres em `127.0.0.1:19642`
  (separado do banco do projeto) e o Omni mantém seu estado em `~/.omni`.

Conexão entre planos: o Genie lê o `.mcp.json` do projeto e se conecta
ao servidor MCP em `http://localhost:8000/sse`, que é a porta exposta no
host pelo contêiner.

A justificativa arquitetural está em
[`docs/specs/2026-04-30-dockerized-setup-design.md`](docs/specs/2026-04-30-dockerized-setup-design.md).

## Pré-requisitos

Pacotes do sistema no host:

- Docker (com o plugin `docker compose`)
- Node.js 18+ **ou** Bun
- `tmux`, `git`, `gh`, `jq`, `yq`, `curl`, `unzip`

Dicas de instalação:

| Ferramenta | Debian/Ubuntu                             | macOS (Homebrew)              |
|------------|-------------------------------------------|-------------------------------|
| docker     | `sudo apt install -y docker.io`           | `brew install --cask docker`  |
| node       | `sudo apt install -y nodejs npm`          | `brew install node`           |
| bun        | `curl -fsSL https://bun.sh/install \| bash` | `brew install bun`         |
| tmux       | `sudo apt install -y tmux`                | `brew install tmux`           |
| gh         | veja https://cli.github.com               | `brew install gh`             |
| jq         | `sudo apt install -y jq`                  | `brew install jq`             |
| yq         | `sudo snap install yq`                    | `brew install yq`             |
| unzip      | `sudo apt install -y unzip`               | `brew install unzip`          |

Você também precisa de uma chave de API da Anthropic **ou** uma sessão
ativa de `claude login`. Se você definir `ANTHROPIC_API_KEY` no `.env`,
o Genie a utiliza ao iniciar.

## Início rápido

```bash
git clone <este repo> && cd conversational-ai-whatsapp-1
cp .env.example .env && "${EDITOR:-nano}" .env  # defina POSTGRES_PASSWORD no mínimo
./scripts/setup.sh                        # instala ferramentas, sobe a stack, registra o agente
./scripts/pair-whatsapp.sh                # escaneia o QR com o app do WhatsApp
```

Após escanear o QR, envie uma mensagem para o número pareado para iniciar
o fluxo de onboarding.

## O que o `setup.sh` faz

`scripts/setup.sh` executa cada passo em ordem, abortando na primeira
falha. Cada passo é idempotente, então re-executar em uma máquina
parcialmente configurada é seguro.

1. `install-deps.sh` — verifica os pacotes do host.
2. `install-claude-code.sh` — instala a CLI do Claude Code globalmente
   se ausente.
3. `install-genie.sh` — executa o instalador oficial do Genie se
   `genie` não estiver no `PATH`.
4. `install-omni.sh` — executa o instalador oficial do Omni se `omni`
   não estiver no `PATH`.
5. `compose-up.sh` — `docker compose up -d --build`, depois aguarda a
   porta TCP do servidor MCP.
6. `register-agent.sh` — adiciona o agente de nutrição ao diretório do
   Genie, lendo `model` e `promptMode` de `agents/nutrition/agent.yaml`.
7. `configure-omni.sh` — cria a instância do WhatsApp, o provider do
   Genie, o agente e a rota que os conecta.

O pareamento é intencionalmente separado (`pair-whatsapp.sh`) porque
exige interação humana.

## Operação manual

Cada script também pode ser executado individualmente. Todos importam
`scripts/lib/common.sh`, que define `set -euo pipefail` e carrega o `.env`.

- `scripts/install-deps.sh` — verifica dependências do host e imprime
  dicas de instalação para as faltantes.
- `scripts/install-claude-code.sh` — instala a CLI do Claude Code.
  No-op se `claude` está no `PATH`.
- `scripts/install-genie.sh` — instala o Genie via instalador upstream.
  No-op se `genie` está no `PATH`.
- `scripts/install-omni.sh` — instala o Omni via instalador upstream.
  No-op se `omni` está no `PATH`.
- `scripts/compose-up.sh` — sobe Postgres, o seeder e o servidor MCP,
  depois aguarda até 60s pela porta TCP do MCP.
- `scripts/register-agent.sh` — registra o agente de nutrição no
  diretório do Genie. Detecta entrada existente pelo nome e pula.
- `scripts/configure-omni.sh` — cria os quatro recursos do Omni
  (instância, provider, agente, rota) de forma idempotente.
- `scripts/pair-whatsapp.sh` — interativo. Detecta pareamento existente
  via `omni instances whoami` e confirma antes de fazer logout e
  re-parear.
- `scripts/doctor.sh` — health check agregado; imprime
  "All systems go ✓" quando tudo passa.
- `scripts/teardown.sh` — reverte o estado do projeto após confirmação
  explícita.

## Health check

`scripts/doctor.sh` executa o seguinte em sequência:

- `genie doctor`
- `omni status`
- `docker compose ps`
- Probe TCP em `localhost:8000`
- `omni providers test <id>` para o provider do Genie

Cada linha é rotulada como `ok:` ou `FAIL:`. O script sai com código 0
apenas quando todos os checks passam.

## Reset

`scripts/teardown.sh` confirma antes de fazer qualquer coisa, e então:

- Deleta a rota, agente, provider e instância do Omni para `nutrition`.
- Remove a entrada `nutrition` do diretório do Genie.
- Executa `docker compose down -v`, descartando o volume `pg_data`.

Ele **não** desinstala Claude Code, Genie ou Omni globalmente. Após o
teardown, `./scripts/setup.sh` reproduz o estado original.

## Testes

A suíte de testes Python vive na raiz do repo em `tests/`, dividida em
`tests/unit/` (funções puras, sem I/O) e `tests/integration/`
(com Postgres via [testcontainers](https://testcontainers.com/)).
A camada de integração sobe `postgres:16-alpine` automaticamente e o
derruba ao final da sessão — não há `TEST_DATABASE_URL` para exportar
nem nada para iniciar à mão.

O venv é criado diretamente a partir do `pyproject.toml` — o extra
`test` em `[project.optional-dependencies]` declara pytest,
testcontainers, psycopg2, anthropic e pyyaml, e o pacote
`nutrition-tools` do MCP é puxado via dependência por path local
declarada na raiz do projeto.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[test]"

pytest tests/unit/         # loop rápido, sem Docker
pytest tests/integration/  # sobe um Postgres efêmero em contêiner
pytest                     # suíte completa
pytest -m "not integration"  # atalho para apenas os unit
```

Se você não quiser ativar o venv, chame os binários diretamente:
`./.venv/bin/pytest`.

A camada de integração precisa de um socket Docker funcional. Se você
consegue rodar `docker compose`, já está pronto.

Se o `pytest` falhar na coleta com `ModuleNotFoundError: No module
named 'nutrition_tools.errors'` (ou outro submódulo similar faltando),
limpe um cache de build obsoleto de uma instalação anterior:

```bash
rm -rf mcp-server/build
pip install -e ./mcp-server  # reinstala o servidor MCP em modo editable
```

`.github/workflows/test.yml` executa o mesmo comando `pytest -v` em todo
push e pull request via GitHub Actions.

### Testes de raciocínio do agente

Um terceiro nível em `tests/agent/` exercita as decisões de chamadas de
ferramenta do agente de nutrição. É dividido em duas camadas:

- **Camada mock** (`tests/agent/mock/`) — dirige o loop do agente com
  `FakeAnthropicClient`, faz asserções sobre sequências exatas de
  chamadas de ferramenta e o estado resultante de `users` /
  `meal_logs`. Sem chave de API, sem custo de LLM real. Roda no
  `pytest` padrão, no hook pytest do pre-commit e em
  `.github/workflows/test.yml`.
- **Camada eval** (`tests/agent/eval/`) — dirige o mesmo harness
  contra a API real da Anthropic usando o system prompt e o modelo de
  produção. Os casos vivem em `tests/agent/eval/cases.yaml` (uma
  entrada YAML por cenário). O runner registra pass/fail por caso e
  faz a suíte falhar quando a taxa agregada de aprovação cai abaixo
  de `PASS_RATE_THRESHOLD = 0.85` (declarado no topo de
  `tests/agent/eval/test_runner.py`).

```bash
pytest tests/agent/mock/                          # camada mock (padrão)
ANTHROPIC_API_KEY=... pytest -m agent_eval -v     # camada eval (API real)
```

Sem `ANTHROPIC_API_KEY` a camada eval pula de forma limpa, então o
`pytest` padrão sempre funciona offline.

A camada eval também roda toda noite via `.github/workflows/eval.yml`
(`workflow_dispatch` + `cron: "0 6 * * *"`). Os resultados aparecem
na aba Actions; falhas notificam pelo caminho de e-mail padrão do
GitHub. O workflow precisa do secret de repositório `ANTHROPIC_API_KEY`
configurado para produzir uma execução verde.

Adicionando novos casos:

- **Mock**: adicione uma função no arquivo `tests/agent/mock/test_*.py`
  relevante seguindo o padrão existente (script `FakeAnthropicClient`,
  asserções sobre `result.tool_calls` e o estado do banco).
- **Eval**: adicione uma entrada YAML em `tests/agent/eval/cases.yaml`.
  Não é necessário alterar código. Ajuste `PASS_RATE_THRESHOLD` apenas
  como um PR explícito.

## Git hooks

O repositório usa [`pre-commit`](https://pre-commit.com/) para rodar
lint, formatação e a suíte de testes antes de cada commit, e para
validar que as mensagens de commit seguem
[Conventional Commits](https://www.conventionalcommits.org/). A
configuração vive em `.pre-commit-config.yaml`.

### Bootstrap (uma vez por clone)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[test,dev]"
pre-commit install
pre-commit install --hook-type commit-msg
```

### O que roda

Em `git commit` os hooks a seguir rodam em ordem, e qualquer falha
aborta o commit:

- Checks de higiene: trailing whitespace, newline no final do arquivo,
  sintaxe YAML / TOML / JSON, marcadores de merge, arquivos grandes.
- `ruff check --fix` e `ruff format` em arquivos Python staged.
- A suíte completa do `pytest`, incluindo o testcontainer do Postgres
  usado nos testes de integração (veja [Testes](#testes)).

Na mensagem do commit, o hook `conventional-pre-commit` valida o
formato e rejeita mensagens que não começam com um dos oito tipos
declarados em [`AGENTS.md`](AGENTS.md#git-commits): `feat`, `fix`,
`docs`, `chore`, `refactor`, `test`, `ci`, `build`.

### Ative o venv antes de commitar

O hook do pytest chama `pytest` do `PATH` (`language: system` na
configuração), então **seu `.venv` precisa estar ativado** quando você
rodar `git commit`. Se o git não encontrar `pytest`, o hook falha com
`Executable pytest not found`. Rode `source .venv/bin/activate` antes
de commitar.

### Escapes

- `git commit --no-verify` — pula todos os hooks, incluindo o
  validador de mensagem de commit. Use com moderação para commits WIP
  que você pretende limpar depois.
- `SKIP=pytest git commit -m "..."` — roda lint, formatação e
  validação de mensagem de commit, mas pula apenas o hook lento de
  testes. Útil quando iterando em docs ou config e você sabe que os
  testes não foram afetados.

A CI roda a suíte completa do pytest em todo push
(`.github/workflows/test.yml`), então qualquer coisa pulada localmente
ainda é capturada antes do merge.

## Solução de problemas

- **QR expirou antes de escanear.** Re-execute
  `./scripts/pair-whatsapp.sh`. O script confirma antes de fazer logout
  de um pareamento ativo.
- **`MCP server did not accept TCP on localhost:8000`.** Inspecione
  `docker compose logs mcp-server`. A causa mais comum é conflito de
  porta na 8000.
- **`omni providers test` falha.** Cheque `omni status` e
  `genie doctor`. O Postgres embutido do Genie escuta em
  `127.0.0.1:19642`; se outro processo segurar essa porta, defina
  `GENIE_PG_PORT` antes de rodar `setup.sh` e reinicie o Genie.
- **`db-seed` reporta "already populated".** Não é uma falha. O seeder
  encurta o caminho quando `taco_foods` já tem linhas.
- **`genie dir add` reclama de entrada existente.** Já tratado pelo
  check de idempotência de `register-agent.sh`; se você executou o
  comando à mão, rode `genie dir rm nutrition` primeiro.
- **Número de WhatsApp banido.** Fora do escopo deste setup. O Baileys
  usa um protocolo não oficial; o único remédio é rotacionar números.

## Layout do projeto

```
.
├── agents/nutrition/         # Definição do agente Genie + prompts
├── db/
│   ├── migrations/           # Schema SQL
│   └── seed/                 # Dockerfile + seed.py + taco.csv (one-shot)
├── mcp-server/               # Servidor MCP em Python (Dockerfile + src + tests)
├── scripts/
│   ├── lib/common.sh         # helpers bash compartilhados
│   ├── setup.sh              # orquestrador de topo
│   ├── teardown.sh           # reverte o estado do projeto
│   ├── doctor.sh             # health check agregado
│   ├── install-*.sh          # bootstrappers de dependências / runtime
│   ├── compose-up.sh         # docker compose up + espera de readiness
│   ├── register-agent.sh     # registro no diretório do Genie
│   ├── configure-omni.sh     # instância/provider/agente/rota do Omni
│   └── pair-whatsapp.sh      # pareamento interativo do QR do WhatsApp
├── docs/
│   ├── 2026-04-30-dockerized-setup-plan.md
│   └── specs/2026-04-30-dockerized-setup-design.md
├── docker-compose.yml
├── .env.example
├── .mcp.json
└── .pre-commit-config.yaml
```

## Adaptando para outro domínio

Os scripts de orquestração são agnósticos de domínio. Para trocar o
agente de nutrição por outro:

1. Substitua `agents/nutrition/` pelo seu próprio diretório de agente e
   atualize `agent.yaml` (`model`, `promptMode`).
2. Substitua `mcp-server/` pelo servidor MCP que expõe as ferramentas
   do seu domínio, mantendo o endpoint SSE em
   `http://localhost:8000/sse` (ou atualize `.mcp.json`).
3. Substitua `db/migrations/` e `db/seed/` pelo seu schema e dados de
   seed.
4. Atualize o nome do agente (`nutrition`) em `register-agent.sh`,
   `configure-omni.sh`, `pair-whatsapp.sh` e `teardown.sh` se quiser
   um identificador diferente.

Os helpers de `scripts/lib/common.sh`, a forma do `docker-compose.yml`
e o fluxo geral permanecem iguais.

## Decisões arquiteturais

Veja [`docs/specs/2026-04-30-dockerized-setup-design.md`](docs/specs/2026-04-30-dockerized-setup-design.md)
para a justificativa de design completa, incluindo por que Genie e Omni
rodam no host em vez de em contêineres.
