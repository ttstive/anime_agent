from typing import Any, Dict, Optional
from mcp.server.fastmcp import FastMCP
import httpx

mcp = FastMCP("Anime_Agent")

JIKAN_BASE = "https://api.jikan.moe/v4"
USER_AGENT = "Anime-agent-app/1.0"



def sucess(tool:str, endpoint:str, params:dict, data:Any, meta:dict | None = None) -> Dict[str, Any]:
    return{
        "ok": True,
        "tool":tool,
        "endpoint":endpoint,
        "paramns":params,
        "data":data,
        "meta":meta or {}
        
    }

def failure(tool:str, endpoint:str, params:dict, error_type:str, message:str, status_code:int | None=None) -> Dict[str, Any]:
    return{
        "ok": True,
        "tool":tool,
        "endpoint":endpoint,
        "paramns":params,
        "error":{
            "type":error_type,
            "message":message,
            "status_code":status_code or {}
        }
        
    }
async def make_request(path: str, params: dict | None = None) -> dict[str, Any] | None:
    url = f"{JIKAN_BASE}{path}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            return {"error": str(e), "url": url}


def _safe_get(d: dict, keys: list[str], default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


@mcp.tool()
async def search_anime(query: str, limit: int = 5) -> str:
    """Search anime by name and return top results with mal_id."""
    data = await make_request("/anime", params={"q": query, "limit": limit})
    items = data.get("data") if isinstance(data, dict) else None

    if not items:
        return f"Nenhum anime encontrado para: {query}"

    lines = []
    for a in items:
        lines.append(
            f"- {a.get('title')} | mal_id={a.get('mal_id')} | score={a.get('score')} | year={a.get('year')}"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_anime_characters(anime_id: int, limit: int = 10) -> str:
    """Get characters from an anime by anime_id (MAL ID)."""
    data = await make_request(f"/anime/{anime_id}/characters")
    items = data.get("data") if isinstance(data, dict) else None

    if not items:
        return f"Nenhum personagem encontrado para anime_id={anime_id}"

    lines = []
    for c in items[:limit]:
        char = c.get("character", {})
        lines.append(
            f"- {char.get('name')} | character_id={char.get('mal_id')} | role={c.get('role')}"
        )

    return "\n".join(lines)


@mcp.tool()
async def get_character_anime(character_id: int, limit: int = 10) -> str:
    """List anime appearances of a character by character_id."""
    data = await make_request(f"/characters/{character_id}/anime")
    items = data.get("data") if isinstance(data, dict) else None

    if not items:
        return f"Nenhum anime encontrado para character_id={character_id}"

    lines = []
    for it in items[:limit]:
        anime = it.get("anime", {})
        lines.append(
            f"- {anime.get('title')} | anime_id={anime.get('mal_id')}"
        )

    return "\n".join(lines)

@mcp.tool()
async def get_anime_episodes(anime_id, limit:int= 10) ->str:
    """List of episodes by especific anime"""
    data = await make_request(f"/anime/{anime_id}/episodes")
    items = data.get("data") if isinstance(data, dict) else None
    
    if not items:
        return f"Nenhum episodio encontrado para o {anime_id}"
    
    lines = []
    for ep in items[:limit]:
           lines.append(
                f"{ep.get('title')} | {ep.get('mal_id')} | aired={ep.get('aired')}"
           )
        
    return "\n".join(lines)

@mcp.tool()
async def get_anime_recommendations(anime_id: int, limit: int = 10) -> str:
    """Recommendations for similar animes."""
    data = await make_request(f"/anime/{anime_id}/recommendations")
    items = data.get("data") if isinstance(data, dict) else None

    if not items:
        return f"Nenhuma recomendação encontrada para anime_id={anime_id}"

    lines = []
    for it in items[:limit]:
        anime = it.get("entry", {})  # <- Jikan usa "entry" em recommendations
        lines.append(
            f"- {anime.get('title')} | anime_id={anime.get('mal_id')} | {anime.get('url')}"
        )

    return "\n".join(lines)




def main():
    mcp.run()


if __name__ == "__main__":
    main()
