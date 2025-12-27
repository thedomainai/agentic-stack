"""
Main entry point for Agentic Stack.

This module initializes and runs the orchestrator with all registered agents.
"""

import asyncio
import signal
import sys
from pathlib import Path

from .agents import (
    ArchitectAgent,
    CoderAgent,
    InfraAgent,
    ResearcherAgent,
    TesterAgent,
)
from .config import get_settings, load_settings
from .core import Orchestrator
from .utils import get_logger

logger = get_logger(__name__)


class AgenticStack:
    """Main application class for Agentic Stack."""

    def __init__(self):
        """Initialize the Agentic Stack application."""
        self._orchestrator: Orchestrator | None = None
        self._shutdown_event = asyncio.Event()
        self._settings = get_settings()

    async def start(self) -> None:
        """Start the Agentic Stack system."""
        logger.info("Starting Agentic Stack")

        # Ensure required directories exist
        self._ensure_directories()

        # Initialize orchestrator
        self._orchestrator = Orchestrator()

        # Register all agent types
        self._register_agents()

        # Start orchestrator
        await self._orchestrator.start()

        # Spawn initial agents
        await self._spawn_initial_agents()

        logger.info("Agentic Stack started successfully")

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        dirs = [
            self._settings.memory_dir,
            self._settings.metrics_dir,
            self._settings.logs_dir,
        ]

        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")

    def _register_agents(self) -> None:
        """Register all available agent types."""
        if not self._orchestrator:
            return

        agent_classes = [
            ("architect", ArchitectAgent),
            ("coder", CoderAgent),
            ("infra", InfraAgent),
            ("researcher", ResearcherAgent),
            ("tester", TesterAgent),
        ]

        for agent_type, agent_class in agent_classes:
            self._orchestrator.register_agent_class(agent_type, agent_class)
            logger.info(f"Registered agent type: {agent_type}")

    async def _spawn_initial_agents(self) -> None:
        """Spawn initial set of agents."""
        if not self._orchestrator:
            return

        # Spawn one of each agent type
        initial_agents = ["coder", "architect", "researcher", "tester", "infra"]

        for agent_type in initial_agents:
            try:
                agent = await self._orchestrator.spawn_agent(agent_type)
                logger.info(f"Spawned initial agent: {agent.agent_id}")
            except Exception as e:
                logger.error(f"Failed to spawn {agent_type} agent: {e}")

    async def stop(self) -> None:
        """Stop the Agentic Stack system."""
        logger.info("Stopping Agentic Stack")

        if self._orchestrator:
            await self._orchestrator.stop()

        logger.info("Agentic Stack stopped")

    async def run(self) -> None:
        """Run the main event loop."""
        await self.start()

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        logger.info("Shutdown requested")
        self._shutdown_event.set()


def setup_signal_handlers(app: AgenticStack) -> None:
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(sig: signal.Signals) -> None:
        logger.info(f"Received signal {sig.name}")
        app.request_shutdown()

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))


async def async_main() -> int:
    """Async main function."""
    # Load settings
    settings_path = Path(".ai/specs/ARCHITECTURE.yaml")
    if settings_path.exists():
        load_settings(settings_path)

    # Create and run application
    app = AgenticStack()

    # Set up signal handlers
    setup_signal_handlers(app)

    try:
        await app.run()
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await app.stop()
        return 130
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        await app.stop()
        return 1


def main() -> int:
    """Main entry point."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    sys.exit(main())
