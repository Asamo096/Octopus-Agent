"""Search tool — web search and code search."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from octopus.core.kernel import Context, ToolResult


class WebSearchTool:
    """Search the web using a search engine."""

    name = "web_search"
    description = "Search the web for information. Returns a list of search results with titles, URLs, and snippets."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        query = args["query"]
        num_results = args.get("num_results", 5)

        try:
            import httpx

            # Use DuckDuckGo HTML API (no key required)
            url = "https://html.duckduckgo.com/html/"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url, data={"q": query}, headers={"User-Agent": "OctopusAgent/0.1"}
                )
                resp.raise_for_status()
                html = resp.text

            # Parse results from HTML
            results = _parse_ddg_html(html, num_results)

            if not results:
                return ToolResult(success=True, output="No search results found.")

            output_lines = []
            for i, r in enumerate(results, 1):
                output_lines.append(f"{i}. **{r['title']}**")
                output_lines.append(f"   {r['url']}")
                output_lines.append(f"   {r['snippet']}")
                output_lines.append("")

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                metadata={"result_count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


class CodeSearchTool:
    """Search for code patterns in the workspace."""

    name = "code_search"
    description = "Search for code patterns in the workspace. Returns matching lines with file paths and line numbers."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "include": {
                "type": "string",
                "description": "File glob to filter (e.g. '*.py')",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results (default: 50)",
                "default": 50,
            },
        },
        "required": ["pattern"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        pattern = args["pattern"]
        include = args.get("include", "*")
        max_results = args.get("max_results", 50)

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return ToolResult(success=False, output=None, error=f"Invalid regex: {e}")

        base = ctx.workspace or Path.cwd()
        matches: list[str] = []

        try:
            for filepath in sorted(base.rglob(include)):
                if not filepath.is_file():
                    continue
                # Skip common non-source directories
                parts = filepath.parts
                if any(
                    p in parts
                    for p in (".git", "node_modules", "__pycache__", ".venv", "venv")
                ):
                    continue
                try:
                    text = filepath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        rel = str(filepath.relative_to(base))
                        matches.append(f"{rel}:{i}: {line.rstrip()}")
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))

        if not matches:
            return ToolResult(success=True, output="No matches found.")
        return ToolResult(
            success=True,
            output="\n".join(matches),
            metadata={
                "match_count": len(matches),
                "truncated": len(matches) >= max_results,
            },
        )


def _parse_ddg_html(html: str, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML results."""
    results = []

    # Find result blocks
    result_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in result_pattern.finditer(html):
        url = match.group(1).strip()
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()

        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= max_results:
                break

    return results


class WebFetchTool:
    """Fetch content from a URL."""

    name = "web_fetch"
    description = "Fetch content from a URL. Returns the page text content."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return (default: 10000)",
                "default": 10000,
            },
        },
        "required": ["url"],
    }

    async def execute(self, args: dict[str, Any], ctx: Context) -> ToolResult:
        url = args["url"]
        max_chars = args.get("max_chars", 10000)

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "OctopusAgent/0.1"})
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if (
                    "text" in content_type
                    or "json" in content_type
                    or "xml" in content_type
                ):
                    text = resp.text[:max_chars]
                else:
                    text = (
                        f"[Binary content: {content_type}, {len(resp.content)} bytes]"
                    )

                return ToolResult(
                    success=True,
                    output=text,
                    metadata={
                        "status_code": resp.status_code,
                        "content_type": content_type,
                    },
                )
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))


def register_search_tools(registry: Any, kernel: Any) -> None:
    """Register search tools."""
    for tool_cls in [WebSearchTool, CodeSearchTool, WebFetchTool]:
        tool = tool_cls()
        registry.register(tool)
        kernel.register_tool(tool)
