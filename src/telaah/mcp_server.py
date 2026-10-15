"""MCP server exposing the telaah tools (stdio): `telaah-mcp` or `python -m telaah.mcp_server`."""
from mcp.server.fastmcp import FastMCP

from telaah import tools

mcp = FastMCP("telaah")


@mcp.tool()
def list_documents() -> list[str]:
    """List the doc_ids available in the corpus."""
    return tools.list_documents()


@mcp.tool()
def search_documents(query: str, k: int = 5) -> list[dict]:
    """Search the corpus; returns the top-k pages as doc_id, page and a snippet."""
    return tools.search_documents(query, k)


@mcp.tool()
def read_page_text(doc_id: str, page: int) -> str:
    """Full text of one page (1-based page number)."""
    return tools.read_page_text(doc_id, page)


@mcp.tool()
def read_page_image(question: str, doc_id: str, page: int) -> str:
    """Read a page image (charts, graphs) with a vision model, focused on the question."""
    return tools.read_page_image(question, doc_id, page)


@mcp.tool()
def calculate(expression: str) -> float:
    """Evaluate an arithmetic expression, e.g. '(120.5 - 98.2) / 98.2 * 100'. Use '.' as decimal point."""
    return tools.calculate(expression)


@mcp.tool()
def check_citation(doc_id: str, page: int, claim: str) -> dict:
    """Check that the cited page exists and every number in the claim appears on it."""
    return tools.check_citation(doc_id, page, claim)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
