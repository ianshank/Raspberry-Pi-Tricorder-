"""MCP Server for Tricorder Neural Platform.

Exposes sensor tools via FastAPI with dynamic tool registry.
All configuration loaded from TricorderConfig — no hardcoded values.
"""

from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone
import asyncio
import logging

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Tool(BaseModel):
    """MCP tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


class ToolCallRequest(BaseModel):
    """Request to call a tool."""
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """Response from a tool call."""
    content: Any
    isError: bool = False


class ToolRegistry:
    """Dynamic registry for MCP tools."""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Tool] = {}

    def register(self, name: str, description: str, input_schema: Dict[str, Any]):
        """Decorator to register a tool function."""
        def decorator(func: Callable):
            self._tools[name] = func
            self._schemas[name] = Tool(
                name=name,
                description=description,
                inputSchema=input_schema,
            )
            logger.info("Registered MCP tool: %s", name)
            return func
        return decorator

    def register_function(
        self, name: str, description: str, input_schema: Dict[str, Any], func: Callable
    ) -> None:
        """Programmatic tool registration (non-decorator)."""
        self._tools[name] = func
        self._schemas[name] = Tool(
            name=name,
            description=description,
            inputSchema=input_schema,
        )
        logger.info("Registered MCP tool: %s", name)

    async def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}. Available: {list(self._tools.keys())}")
        func = self._tools[name]
        if asyncio.iscoroutinefunction(func):
            return await func(**arguments)
        return func(**arguments)

    def list_tools(self) -> List[Tool]:
        return list(self._schemas.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_count(self) -> int:
        return len(self._tools)


# Global registry instance
tool_registry = ToolRegistry()


def create_app(
    config: Optional[Dict[str, Any]] = None,
    registry: Optional[ToolRegistry] = None,
) -> FastAPI:
    """
    Create FastAPI MCP server app.

    Args:
        config: MCP server configuration dict
        registry: Optional tool registry (defaults to global)
    """
    config = config or {}
    reg = registry or tool_registry

    app = FastAPI(
        title=config.get("title", "Tricorder MCP Server"),
        version=config.get("version", "1.0.0"),
    )

    auth_enabled = config.get("auth_enabled", False)
    api_key = config.get("api_key")

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if auth_enabled and api_key:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if request.url.path not in ("/health", "/docs", "/openapi.json"):
                if token != api_key:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing API key"},
                    )
        return await call_next(request)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools_registered": reg.tool_count,
        }

    @app.get("/tools")
    async def get_tools():
        return [t.model_dump() for t in reg.list_tools()]

    @app.post("/tools/call")
    async def call_tool(request: ToolCallRequest):
        try:
            result = await reg.call(request.name, request.arguments)
            return ToolCallResponse(content=result, isError=False)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except TypeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid arguments: {e}")
        except Exception as e:
            logger.error("Tool call %s failed: %s", request.name, e, exc_info=True)
            return ToolCallResponse(content={"error": str(e)}, isError=True)

    return app


def main():
    """Entry point for running MCP server standalone."""
    import uvicorn
    from utils.config import load_config

    config = load_config()
    app = create_app(config=config.mcp_server.model_dump())
    uvicorn.run(
        app,
        host=config.mcp_server.host,
        port=config.mcp_server.port,
    )


if __name__ == "__main__":
    main()
