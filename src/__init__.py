"""
Agentic Stack - Autonomous AI Agent Orchestration Platform

This package provides the core infrastructure for orchestrating
autonomous AI agents that collaborate to complete complex tasks.
"""

__version__ = "0.1.0"
__author__ = "Agentic Stack Team"

from .core import BaseAgent, AgentStatus, Orchestrator
from .agents import (
    ArchitectAgent,
    CoderAgent,
    InfraAgent,
    ResearcherAgent,
    TesterAgent,
)
from .config import Settings, get_settings, load_settings

__all__ = [
    # Core
    "BaseAgent",
    "AgentStatus",
    "Orchestrator",
    # Agents
    "ArchitectAgent",
    "CoderAgent",
    "InfraAgent",
    "ResearcherAgent",
    "TesterAgent",
    # Config
    "Settings",
    "get_settings",
    "load_settings",
    # Metadata
    "__version__",
    "__author__",
]
