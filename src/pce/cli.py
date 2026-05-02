"""CLI entry point: `pce` command."""
import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="pce", help="Personal Context Engine")
console = Console()


def _run(coro):
    return asyncio.run(coro)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8766,
    reload: bool = False,
):
    """Start the PCE server."""
    import uvicorn
    uvicorn.run("pce.main:app", host=host, port=port, reload=reload)


@app.command()
def ingest(
    directory: Path = typer.Argument(..., help="Directory to scan and ingest"),
):
    """Ingest all files from a directory into the context store."""
    async def _ingest():
        from pce.main import startup
        await startup()
        from pce.connectors.files import scan_directory
        count = await scan_directory(directory)
        console.print(f"[green]Ingested {count} files from {directory}[/green]")

    _run(_ingest())


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(10, "--top-k", "-k"),
):
    """Search ingested content."""
    async def _search():
        from pce.db.session import get_session_factory
        from pce.retrieval.search import hybrid_search

        factory = get_session_factory()
        async with factory() as session:
            results = await hybrid_search(query, session, top_k=top_k)

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(title=f"Results for: {query}")
        table.add_column("Score", style="cyan", width=6)
        table.add_column("Source", style="magenta", width=8)
        table.add_column("Title", style="bold")
        table.add_column("Snippet", no_wrap=False, max_width=60)

        for r in results:
            table.add_row(
                f"{r.score:.3f}",
                r.source,
                r.title,
                r.snippet[:120],
            )
        console.print(table)

    _run(_search())


@app.command()
def embed():
    """Run the embedding worker once (embeds all pending chunks)."""
    async def _embed():
        from pce.ingestion.embedder import embed_pending
        count = await embed_pending()
        console.print(f"[green]Embedded {count} chunks.[/green]")

    _run(_embed())


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask"),
    top_k: int = typer.Option(10, "--top-k", "-k"),
):
    """Ask a question — retrieves context and answers via LLM."""
    async def _ask():
        from pce.db.session import get_session_factory
        from pce.llm.router import ask as llm_ask
        from pce.retrieval.search import hybrid_search

        factory = get_session_factory()
        async with factory() as session:
            results = await hybrid_search(question, session, top_k=top_k)

        if not results:
            console.print("[yellow]No relevant context found.[/yellow]")
            return

        sources = [
            {
                "item_id": r.item_id,
                "title": r.title,
                "source": r.source,
                "path": r.path,
                "url": r.url,
                "snippet": r.snippet,
                "chunks": r.chunks,
            }
            for r in results
        ]

        console.print(f"\n[dim]Searching {len(results)} sources...[/dim]")
        llm_resp = await llm_ask(question, sources)

        console.print(f"\n[bold cyan]Answer[/bold cyan] [dim]({llm_resp.backend}, {llm_resp.latency_ms}ms)[/dim]\n")
        console.print(llm_resp.answer)

        console.print("\n[bold]Sources[/bold]")
        for i, r in enumerate(results, start=1):
            label = r.title or r.path or r.url or r.item_id
            console.print(f"  [cyan][{i}][/cyan] {label} [dim]({r.source})[/dim]")

    _run(_ask())


@app.command()
def team(
    task: str = typer.Argument(..., help="Task for the team to complete"),
):
    """Run a team of AI agents (Researcher → Planner → Coder → Reviewer) on a task.

    Requires PCE_ANTHROPIC_API_KEY to be set.
    """
    async def _team():
        from pce.agents.orchestrator import run_team
        from pce.db.session import get_session_factory

        console.print(f"\n[bold cyan]Team Task:[/bold cyan] {task}\n")

        factory = get_session_factory()
        async with factory() as session:
            result = await run_team(task, session)

        role_colors = {
            "researcher": "blue",
            "planner": "yellow",
            "coder": "green",
            "reviewer": "magenta",
        }
        for agent_out in result.agents:
            color = role_colors.get(agent_out.role, "white")
            console.rule(
                f"[bold {color}]{agent_out.role.title()}[/bold {color}]"
                f"  [dim]{agent_out.tool_calls} tool call(s)[/dim]"
            )
            console.print(agent_out.text)
            console.print()

        console.rule("[bold green]Team report saved to Comtext[/bold green]")

    _run(_team())


if __name__ == "__main__":
    app()
