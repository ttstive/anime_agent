import os
import sys
import json
import asyncio
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from google import genai
from google.genai import types

load_dotenv()

console = Console()


SYSTEM_PROMPT = """
Você é um assistente especialista em animes.
Você possui acesso a ferramentas MCP (Jikan API) e deve usar ferramentas sempre que a pergunta exigir dados.

Regras:
- Não invente dados
- Se faltar informação, use tools
- Prefira buscar IDs via search_anime antes de outras tools
- Se o usuário mencionar um anime por nome e não fornecer anime_id, faça search_anime
- Responda em português
- Formato da resposta:
  1) Resposta curta
  2) Detalhes (bullets)
  3) Tools usadas (se houver)
"""


class MCPAnimeClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

        # memória simples do client
        self.memory: Dict[str, Any] = {
            "last_anime": None,         # {"title":..., "anime_id":...}
            "last_character": None      # {"name":..., "character_id":...}
        }

        # Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY não encontrado. Coloque no .env")

        self.gemini = genai.Client(api_key=api_key)

    async def connect_server(self, path_to_server: str):
        command = "python"
        server_params = StdioServerParameters(
            command=command,
            args=[path_to_server],
            env=None,
        )

        transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = transport

        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.stdio, self.write)
        )
        await self.session.initialize()

        tools = (await self.session.list_tools()).tools
        console.print(Panel.fit(
            f"✅ Conectado ao MCP Server.\nTools disponíveis: {len(tools)}",
            title="MCP Client"
        ))

    async def close(self):
        await self.exit_stack.aclose()

    # -----------------------------
    # MCP tool helpers
    # -----------------------------
    async def list_tools(self):
        resp = await self.session.list_tools()
        return resp.tools

    async def call_tool(self, tool_name: str, args: Dict[str, Any]):
        return await self.session.call_tool(tool_name, args)

    # -----------------------------
    # Terminal UI helpers
    # -----------------------------
    def show_help(self):
        console.print(Panel(
            "\n".join([
                "[bold]Comandos:[/bold]",
                "  help                     -> mostra comandos",
                "  tools                    -> lista tools MCP",
                "  use <tool> <json>         -> chama tool manualmente",
                "  anime <nome>              -> search_anime e guarda anime_id",
                "  chars [limit]             -> personagens do último anime",
                "  eps [limit]               -> episódios do último anime",
                "  recs [limit]              -> recomendações do último anime",
                "  clear                     -> limpa memória",
                "  ask <pergunta>            -> pergunta usando Gemini + tools",
                "  quit                      -> sair",
            ]),
            title="Ajuda",
        ))

    async def show_tools_table(self):
        tools = await self.list_tools()
        table = Table(title="Tools MCP disponíveis")
        table.add_column("Nome", style="bold")
        table.add_column("Descrição")
        table.add_column("Schema (inputs)", overflow="fold")

        for t in tools:
            table.add_row(
                t.name,
                t.description or "",
                json.dumps(t.inputSchema, ensure_ascii=False),
            )
        console.print(table)

    def _get_last_anime_id(self) -> Optional[int]:
        last = self.memory.get("last_anime")
        if not last:
            return None
        return last.get("anime_id")

    # -----------------------------
    # Gemini tool loop (multi-step)
    # -----------------------------
    async def ask_with_agent(self, query: str, max_steps: int = 3) -> str:
        tools = await self.list_tools()

        # transformar tools MCP em function declarations pro Gemini
        function_decls = []
        for t in tools:
            function_decls.append(
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description or "",
                    parameters=t.inputSchema,
                )
            )

        tool_cfg = types.Tool(function_declarations=function_decls)

        # adiciona memória no contexto
        mem_context = f"MEMÓRIA_ATUAL={json.dumps(self.memory, ensure_ascii=False)}"

        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=f"{SYSTEM_PROMPT}\n\n{mem_context}\n\nPergunta: {query}")]
            )
        ]

        used_tools: List[str] = []

        for step in range(max_steps):
            resp = self.gemini.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=[tool_cfg],
                    temperature=0.3,
                )
            )

            # se não tiver tool call, é resposta final
            if not resp.candidates or not resp.candidates[0].content.parts:
                return "❌ Resposta vazia do modelo."

            parts = resp.candidates[0].content.parts

            # tool calls
            tool_calls = [p.function_call for p in parts if p.function_call]
            text_parts = [p.text for p in parts if p.text]

            if tool_calls:
                for call in tool_calls:
                    tool_name = call.name
                    tool_args = dict(call.args or {})
                    used_tools.append(tool_name)

                    console.print(Panel.fit(
                        f"[bold]Tool:[/bold] {tool_name}\n[bold]Args:[/bold] {json.dumps(tool_args, ensure_ascii=False)}",
                        title=f"Step {step+1} - Tool Call",
                        border_style="cyan"
                    ))

                    result = await self.call_tool(tool_name, tool_args)

                    # MCP result geralmente vem como list de content
                    # vamos converter em texto simples
                    result_text = ""
                    if result and result.content:
                        # result.content é lista
                        result_text = "\n".join([c.text for c in result.content if hasattr(c, "text")])

                    console.print(Panel.fit(
                        result_text[:1500] + ("..." if len(result_text) > 1500 else ""),
                        title="Tool Result",
                        border_style="green"
                    ))

                    # atualizar memória quando fizer sentido
                    self._update_memory_from_tool(tool_name, tool_args, result_text)

                    # alimentar Gemini com tool result
                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part(function_call=call)]
                        )
                    )
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name=tool_name,
                                        response={"result": result_text}
                                    )
                                )
                            ]
                        )
                    )

                continue  # volta para próxima iteração

            # se chegou aqui sem tool_calls, devolve texto final
            final = "\n".join([t for t in text_parts if t])
            if used_tools:
                final += "\n\n[Tools usadas: " + ", ".join(sorted(set(used_tools))) + "]"
            return final

        return "⚠️ Atingi o limite de passos do agente. Tente refinar a pergunta."

    def _update_memory_from_tool(self, tool_name: str, tool_args: Dict[str, Any], tool_result_text: str):
        """
        Memória simples:
        - se search_anime for usado, tenta extrair o primeiro mal_id retornado
        """
        if tool_name == "search_anime":
            # tenta extrair "mal_id=123"
            import re
            m = re.search(r"mal_id=(\d+)", tool_result_text)
            if m:
                anime_id = int(m.group(1))
                self.memory["last_anime"] = {"title": tool_args.get("query"), "anime_id": anime_id}

    # -----------------------------
    # Command loop
    # -----------------------------
    async def loop(self):
        self.show_help()

        while True:
            try:
                cmd = console.input("\n[bold cyan]anime-agent> [/bold cyan]").strip()
                if not cmd:
                    continue

                if cmd in ("quit", "exit"):
                    break

                if cmd == "help":
                    self.show_help()
                    continue

                if cmd == "tools":
                    await self.show_tools_table()
                    continue

                if cmd == "clear":
                    self.memory = {"last_anime": None, "last_character": None}
                    console.print("🧹 Memória limpa.")
                    continue

                if cmd.startswith("use "):
                    # use <tool> <json>
                    _, tool_name, json_args = cmd.split(" ", 2)
                    args = json.loads(json_args)
                    result = await self.call_tool(tool_name, args)
                    txt = "\n".join([c.text for c in result.content if hasattr(c, "text")])
                    console.print(Panel(txt, title=f"Tool Result: {tool_name}"))
                    continue

                if cmd.startswith("anime "):
                    query = cmd.replace("anime ", "", 1).strip()
                    result = await self.call_tool("search_anime", {"query": query, "limit": 5})
                    txt = "\n".join([c.text for c in result.content if hasattr(c, "text")])
                    console.print(Panel(txt, title="search_anime"))
                    self._update_memory_from_tool("search_anime", {"query": query}, txt)
                    console.print(f"📌 last_anime: {self.memory['last_anime']}")
                    continue

                if cmd.startswith("chars"):
                    limit = 10
                    parts = cmd.split()
                    if len(parts) == 2:
                        limit = int(parts[1])
                    anime_id = self._get_last_anime_id()
                    if not anime_id:
                        console.print("⚠️ Nenhum anime selecionado. Use: anime Naruto")
                        continue
                    result = await self.call_tool("get_anime_characters", {"anime_id": anime_id, "limit": limit})
                    txt = "\n".join([c.text for c in result.content if hasattr(c, "text")])
                    console.print(Panel(txt, title="get_anime_characters"))
                    continue

                if cmd.startswith("eps"):
                    limit = 10
                    parts = cmd.split()
                    if len(parts) == 2:
                        limit = int(parts[1])
                    anime_id = self._get_last_anime_id()
                    if not anime_id:
                        console.print("⚠️ Nenhum anime selecionado. Use: anime Naruto")
                        continue
                    result = await self.call_tool("get_anime_episodes", {"anime_id": anime_id, "limit": limit})
                    txt = "\n".join([c.text for c in result.content if hasattr(c, "text")])
                    console.print(Panel(txt, title="get_anime_episodes"))
                    continue

                if cmd.startswith("recs"):
                    limit = 10
                    parts = cmd.split()
                    if len(parts) == 2:
                        limit = int(parts[1])
                    anime_id = self._get_last_anime_id()
                    if not anime_id:
                        console.print("⚠️ Nenhum anime selecionado. Use: anime Naruto")
                        continue
                    result = await self.call_tool("get_anime_recommendations", {"anime_id": anime_id, "limit": limit})
                    txt = "\n".join([c.text for c in result.content if hasattr(c, "text")])
                    console.print(Panel(txt, title="get_anime_recommendations"))
                    continue

                if cmd.startswith("ask "):
                    query = cmd.replace("ask ", "", 1).strip()
                    answer = await self.ask_with_agent(query)
                    console.print(Panel(answer, title="Resposta"))
                    continue

                # fallback: qualquer coisa vira ask
                answer = await self.ask_with_agent(cmd)
                console.print(Panel(answer, title="Resposta"))

            except KeyboardInterrupt:
                console.print("\n👋 Saindo...")
                break
            except Exception as e:
                console.print(f"[red]Erro:[/red] {e}")


async def main():
    if len(sys.argv) < 2:
        print("Uso: python client.py /Users/elmaia/Development/anime_agent/mcp_server/server.py")
        sys.exit(1)

    client = MCPAnimeClient()
    try:
        await client.connect_server(sys.argv[1])
        await client.loop()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
