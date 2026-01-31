# 🎌 Anime Agent — MCP + Jikan API + Google Gemini

Um projeto completo de **Agente de IA com MCP (Model Context Protocol)**, focado em fornecer informações precisas sobre o universo dos animes utilizando ferramentas externas e raciocínio avançado.

O ecossistema é composto por:
* **MCP Server (FastMCP):** Expõe ferramentas (tools) para consultar a **Jikan API v4** (MyAnimeList).
* **MCP Client:** Interface interativa via terminal que utiliza o **Google Gemini** para raciocínio, planejamento e encadeamento de ferramentas (*tool chaining*).

> 🎯 **Objetivo:** Criar um agente confiável e robusto, reduzindo alucinações de modelos de linguagem ao basear as respostas em dados reais e atualizados.

---

## ✨ Principais Features

### ✅ MCP Server (FastMCP + Jikan API)
* Integração direta com a **Jikan API v4**.
* Requests assíncronos de alta performance com `httpx.AsyncClient`.
* **Tools implementadas:**
    * `search_anime(query, limit)`
    * `get_anime_characters(anime_id, limit)`
    * `get_character_anime(character_id, limit)`
    * `get_anime_episodes(anime_id, limit)`
    * `get_anime_recommendations(anime_id, limit)`
* **Retorno padronizado:** Estrutura de `success()` e `failure()` para facilitar o parsing do LLM.

### ✅ MCP Client (Terminal Interativo + Gemini)
* **Interface Rica:** UI no terminal desenvolvida com a biblioteca **Rich**.
* **Modo Agent:** O Gemini decide automaticamente quais ferramentas chamar e em qual ordem.
* **Memória de Contexto:** Armazena o último `anime_id` selecionado para permitir comandos rápidos (ex: buscar personagens sem precisar digitar o ID novamente).
* **Multi-step Tool Chaining:** Capacidade de realizar várias buscas sequenciais para responder perguntas complexas.

---

## 🧠 Visão Técnica (Arquitetura)

O MCP (Model Context Protocol) separa a camada de **dados/ferramentas** da camada de **inteligência/raciocínio**.

**Fluxo de Execução:**
1. Usuário faz uma pergunta no terminal.
2. O Client envia o prompt para o Gemini.
3. O Gemini identifica a necessidade de dados externos e solicita uma *tool call*.
4. O Client executa a ferramenta no Server via `stdio`.
5. O resultado retorna ao Gemini, que sintetiza a resposta final.

```text
Usuário (Terminal)
│
▼
MCP Client (Gemini Agent)
│ ├── reasoning / planning
│ ├── tool selection
│ └── tool chaining (multi-step)
▼
MCP Server (FastMCP Tools)
│
▼
Jikan API v4 (MyAnimeList)


anime_agent/
├── mcp_server/
│   ├── server.py
│   └── pyproject.toml
├── mcp_client/
│   ├── client.py
│   └── pyproject.toml
├── .env
├── .gitignore└── README.md
```
git clone [https://github.com/ttstive/anime_agent.git](https://github.com/ttstive/anime_agent.git)
cd anime_agent

<img width="2348" height="1598" alt="image" src="https://github.com/user-attachments/assets/5397764e-dc74-4e31-9ff8-3b1770466345" />
<img width="2348" height="1598" alt="image" src="https://github.com/user-attachments/assets/d11eae38-8e0d-4b32-a288-98d2391d0966" />


