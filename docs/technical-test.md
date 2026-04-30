# Teste Técnico
## Agente Conversacional no WhatsApp

## Contexto

O objetivo é avaliar a capacidade de construir um agente de IA funcional que opera em um canal de mensageria real, não apenas um chatbot com prompt fixo.

A Namastex opera com duas ferramentas internas open source:

- **Genie** como orquestrador de agentes baseado em Claude Code. Gerencia times, sessões, memória e comunicação entre agentes. Funciona como o "cérebro", recebe mensagens, processa com Claude e devolve respostas.
- **Omni** como plataforma omnichannel que conecta canais de mensageria (WhatsApp, Telegram, Discord) a provedores de agentes. Funciona como a "ponte", recebe mensagens do canal nativo e roteia para o agente.

## Desafio

Construir um agente conversacional que atende no WhatsApp, usando Genie como orquestrador e Omni como bridge de canal.

O agente deve:

- Receber mensagens de WhatsApp via Omni
- Processar com Claude via Genie (agente nativo)
- Responder de volta pelo WhatsApp
- Ter um propósito claro (o candidato escolhe o domínio)
- Usar pelo menos uma ferramenta externa (MCP server, API, banco de dados, etc.)

**Importante:** O agente NÃO deve ser apenas um wrapper de prompt. Ele deve ter capacidade real de acessar dados, executar ações, ou integrar com sistemas externos.

Para ajudar a pensar no escopo, aqui estão os tipos de agentes que candidatos anteriores construíram. Use como inspiração, quanto mais original e útil, melhor:

- Agente de BI que consulta banco de dados e responde perguntas sobre vendas, clientes e financeiro
- Agente pessoal que gerencia agenda, tarefas e lembretes
- Agente de suporte que consulta base de conhecimento e resolve dúvidas
- Agente de DevOps que monitora deploys e notifica sobre falhas

O candidato tem total liberdade para escolher o domínio. O que importa é que o agente resolva algo real.

## Arquitetura Exemplo

```
Usuário WhatsApp → Omni (Baileys) → Genie Agent → Claude Code → Ferramentas
```

Fluxo de mensagens:

1. Usuário envia mensagem
2. Omni normaliza a mensagem e roteia
3. Genie faz spawn de sessão + contexto
4. Claude Code executa tool call (API/DB/MCP) — loop com múltiplas ferramentas
5. Ferramentas retornam resultado
6. Claude Code retorna resposta processada ao Genie
7. Genie entrega resposta ao Omni
8. Omni responde no WhatsApp

**Camadas:**
- Camada 1: Canal (Omni)
- Camada 2: Orquestração (Genie)
- Camada 3: Capacidades (Claude Code + Ferramentas)

## Requisitos

### Obrigatórios

1. WhatsApp como canal de entrada (via Omni com Baileys)
2. Genie como orquestrador do agente (Claude Code nativo)
3. Omni como bridge entre WhatsApp e Genie
4. Pelo menos uma ferramenta/integração real (MCP, API, DB, etc.)
5. Agente com propósito claro e funcional
6. Código disponível em repositório público no GitHub
7. README com instruções de setup, execução e adaptações técnicas

### Diferenciais (espaço para criatividade)

1. Complexidade e utilidade do agente (quanto mais real, melhor)
2. Qualidade das ferramentas/integrações construídas
3. Robustez em tratamento de erros, edge cases, mensagens inesperadas
4. Memória e contexto entre mensagens
5. Documentação de decisões arquiteturais
6. Testes automatizados

### Recursos

- [github.com/automagik-dev/genie](https://github.com/automagik-dev/genie)
- [github.com/automagik-dev/omni](https://github.com/automagik-dev/omni)

Esses repositórios contêm documentação, exemplos e instruções de instalação. Parte do teste é navegar essa documentação e entender como as peças se encaixam, de modo que você se torne nativo em Genie e Omni.

## Entrega

1. Repositório público no GitHub
2. README com instruções de setup, execução e adaptações técnicas
3. Agente funcional rodando no WhatsApp (disponibilizado um número para contatarmos)

## Avaliação

### Engenharia de agentes

O agente funciona end-to-end? Recebe mensagem no WhatsApp e responde com inteligência? As ferramentas agregam valor real ou são decorativas? O agente é autônomo ou precisa de intervenção manual?

### Integração de sistemas

Soube conectar Genie + Omni + WhatsApp? Entendeu o fluxo de mensagens entre as camadas? A integração é robusta ou quebra com facilidade?

### Criatividade e propósito

Que problema o agente resolve? É útil de verdade? O candidato mostrou visão de produto ou apenas implementação técnica?

### Qualidade de código

O código é limpo, bem estruturado, documentado? Segue boas práticas? O setup é reproduzível (docker-compose, scripts, etc.)?
