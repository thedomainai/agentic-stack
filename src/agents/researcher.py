"""
Researcher Agent - Handles research and information gathering.

This agent specializes in searching, analyzing documentation,
gathering information, and synthesizing findings.
"""

from typing import Any

import anthropic

from ..config import get_settings
from ..core.agent_base import BaseAgent, TaskResult
from ..services.rabbitmq_client import TaskMessage


class ResearcherAgent(BaseAgent):
    """
    Agent specialized in research and information gathering.

    Capabilities:
    - Documentation search and analysis
    - Information synthesis
    - Competitive analysis
    - Technology evaluation
    """

    AGENT_TYPE = "researcher"
    CAPABILITIES = [
        "task.assign",
        "research.search",
        "research.analyze",
        "research.summarize",
        "research.compare",
        "docs.search",
    ]

    def __init__(self, **kwargs):
        """Initialize the Researcher agent."""
        super().__init__(**kwargs)
        self._settings = get_settings()
        self._anthropic: anthropic.AsyncAnthropic | None = None

    async def start(self) -> None:
        """Start the agent and initialize LLM client."""
        await super().start()

        api_key = self._settings.llm.api_key
        if api_key:
            self._anthropic = anthropic.AsyncAnthropic(api_key=api_key)
            self.logger.info("Anthropic client initialized")
        else:
            self.logger.warning("No API key configured - LLM calls will fail")

    async def execute_task(self, message: TaskMessage) -> TaskResult:
        """
        Execute a research task.

        Args:
            message: Task message with action and payload

        Returns:
            TaskResult with research findings or error
        """
        action = message.action
        payload = message.payload

        self.logger.info(f"Executing action: {action}")

        if action == "task.assign":
            return await self._handle_generic_task(payload)
        elif action == "research.search":
            return await self._search_information(payload)
        elif action == "research.analyze":
            return await self._analyze_content(payload)
        elif action == "research.summarize":
            return await self._summarize_content(payload)
        elif action == "research.compare":
            return await self._compare_options(payload)
        elif action == "docs.search":
            return await self._search_documentation(payload)
        else:
            return TaskResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _handle_generic_task(self, payload: dict[str, Any]) -> TaskResult:
        """Handle a generic research task."""
        title = payload.get("title", "")
        description = payload.get("description", "")

        prompt = f"""You are a research specialist. Analyze the following research task
and provide comprehensive findings.

Task: {title}

Description: {description}

Provide your response in the following format:
1. Research Scope: What needs to be investigated
2. Key Findings: Main discoveries and insights
3. Sources: Types of sources that would be relevant
4. Analysis: Interpretation of findings
5. Recommendations: Suggested next steps based on research"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "response": response,
                    "task_title": title,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to generate response from LLM",
            )

    async def _search_information(self, payload: dict[str, Any]) -> TaskResult:
        """Search for information on a topic."""
        query = payload.get("query", "")
        scope = payload.get("scope", "general")
        depth = payload.get("depth", "standard")

        prompt = f"""Research the following topic and provide comprehensive information:

Query: {query}
Scope: {scope}
Depth: {depth}

Provide:
1. Overview: General understanding of the topic
2. Key Concepts: Important terms and ideas
3. Current State: Latest developments and trends
4. Best Practices: Industry standards and recommendations
5. Common Pitfalls: Mistakes to avoid
6. Resources: Types of resources for further learning"""

        response = await self._call_llm(prompt)

        if response:
            await self._log_discovery(
                category="research_finding",
                title=f"Research on: {query[:50]}",
                description=f"Completed {depth} research with {scope} scope",
                confidence=0.75,
                tags=["research", scope, depth],
            )

            return TaskResult(
                success=True,
                result={
                    "findings": response,
                    "query": query,
                    "scope": scope,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to search information",
            )

    async def _analyze_content(self, payload: dict[str, Any]) -> TaskResult:
        """Analyze provided content."""
        content = payload.get("content", "")
        analysis_type = payload.get("analysis_type", "comprehensive")
        questions = payload.get("questions", [])

        questions_text = "\n".join(f"- {q}" for q in questions) if questions else ""

        prompt = f"""Analyze the following content:

Content:
{content}

Analysis Type: {analysis_type}

{f"Specific Questions:{chr(10)}{questions_text}" if questions_text else ""}

Provide:
1. Summary: Key points from the content
2. Analysis: Deep dive into the material
3. Insights: Non-obvious observations
4. Implications: What this means in practice
5. Gaps: Information that appears to be missing
{f"6. Answers: Responses to specific questions" if questions else ""}"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "analysis": response,
                    "analysis_type": analysis_type,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to analyze content",
            )

    async def _summarize_content(self, payload: dict[str, Any]) -> TaskResult:
        """Summarize provided content."""
        content = payload.get("content", "")
        length = payload.get("length", "medium")
        focus = payload.get("focus", [])
        format_type = payload.get("format", "prose")

        focus_text = "\n".join(f"- {f}" for f in focus) if focus else "All aspects"

        prompt = f"""Summarize the following content:

Content:
{content}

Summary Length: {length}
Format: {format_type}

Focus Areas:
{focus_text}

Requirements:
- Capture the essential information
- Maintain accuracy
- Use clear, concise language
- Organize logically
{f"- Present as bullet points" if format_type == "bullets" else ""}"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "summary": response,
                    "length": length,
                    "format": format_type,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to summarize content",
            )

    async def _compare_options(self, payload: dict[str, Any]) -> TaskResult:
        """Compare multiple options or alternatives."""
        options = payload.get("options", [])
        criteria = payload.get("criteria", [])
        context = payload.get("context", "")

        options_text = "\n".join(f"- {opt}" for opt in options)
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "Standard evaluation criteria"

        prompt = f"""Compare the following options:

Options:
{options_text}

{f"Context: {context}" if context else ""}

Evaluation Criteria:
{criteria_text}

Provide:
1. Overview: Brief description of each option
2. Comparison Matrix: How each option scores on criteria
3. Strengths & Weaknesses: Pros and cons of each
4. Use Cases: When each option is most appropriate
5. Recommendation: Best choice for different scenarios"""

        response = await self._call_llm(prompt)

        if response:
            await self._log_decision(
                decision_type="comparison_analysis",
                context=f"Compared {len(options)} options",
                options_considered=[{"option": opt} for opt in options],
                chosen_option="analysis_provided",
                rationale="Multi-criteria comparison completed",
            )

            return TaskResult(
                success=True,
                result={
                    "comparison": response,
                    "options": options,
                    "criteria": criteria,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to compare options",
            )

    async def _search_documentation(self, payload: dict[str, Any]) -> TaskResult:
        """Search and analyze documentation."""
        topic = payload.get("topic", "")
        doc_type = payload.get("doc_type", "technical")
        questions = payload.get("questions", [])

        questions_text = "\n".join(f"- {q}" for q in questions) if questions else ""

        prompt = f"""Search and analyze documentation for the following:

Topic: {topic}
Documentation Type: {doc_type}

{f"Questions to Answer:{chr(10)}{questions_text}" if questions_text else ""}

Provide:
1. Documentation Overview: What documentation typically covers for this topic
2. Key Sections: Important parts of the documentation
3. Common Patterns: Typical usage patterns and examples
4. API/Interface Details: Key interfaces if applicable
5. Configuration: Common configuration options
6. Troubleshooting: Common issues and solutions
{f"7. Question Answers: Specific answers to questions" if questions else ""}"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "documentation": response,
                    "topic": topic,
                    "doc_type": doc_type,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to search documentation",
            )

    async def _call_llm(self, prompt: str) -> str | None:
        """Call the LLM API with a prompt."""
        if not self._anthropic:
            self.logger.error("Anthropic client not initialized")
            return None

        try:
            response = await self._anthropic.messages.create(
                model=self._settings.llm.model,
                max_tokens=self._settings.llm.max_tokens,
                temperature=self._settings.llm.temperature,
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )

            if response.content:
                return response.content[0].text

            return None

        except anthropic.APIError as e:
            self.logger.error(f"LLM API error: {e}")
            return None
        except Exception as e:
            self.logger.exception(f"Unexpected error calling LLM: {e}")
            return None
