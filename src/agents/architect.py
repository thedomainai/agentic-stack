"""
Architect Agent - Handles design and code review tasks.

This agent specializes in architecture design, code review,
refactoring recommendations, and technical decision-making.
"""

from typing import Any

import anthropic

from ..config import get_settings
from ..core.agent_base import BaseAgent, TaskResult
from ..services.rabbitmq_client import TaskMessage


class ArchitectAgent(BaseAgent):
    """
    Agent specialized in software architecture and design.

    Capabilities:
    - Architecture design and review
    - Code review and quality assessment
    - Refactoring recommendations
    - Technical decision analysis
    """

    AGENT_TYPE = "architect"
    CAPABILITIES = [
        "task.assign",
        "design.review",
        "design.create",
        "code.review",
        "refactor.recommend",
        "decision.analyze",
    ]

    def __init__(self, **kwargs):
        """Initialize the Architect agent."""
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
        Execute an architecture task.

        Args:
            message: Task message with action and payload

        Returns:
            TaskResult with analysis or error
        """
        action = message.action
        payload = message.payload

        self.logger.info(f"Executing action: {action}")

        if action == "task.assign":
            return await self._handle_generic_task(payload)
        elif action == "design.review":
            return await self._review_design(payload)
        elif action == "design.create":
            return await self._create_design(payload)
        elif action == "code.review":
            return await self._review_code(payload)
        elif action == "refactor.recommend":
            return await self._recommend_refactoring(payload)
        elif action == "decision.analyze":
            return await self._analyze_decision(payload)
        else:
            return TaskResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _handle_generic_task(self, payload: dict[str, Any]) -> TaskResult:
        """Handle a generic architecture task."""
        title = payload.get("title", "")
        description = payload.get("description", "")

        prompt = f"""You are a senior software architect. Analyze the following task
and provide architectural guidance.

Task: {title}

Description: {description}

Provide your response in the following format:
1. Analysis: Understanding of the requirements
2. Architecture Recommendation: Suggested design approach
3. Key Considerations: Important factors to consider
4. Potential Risks: Areas that need attention
5. Next Steps: Recommended actions"""

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

    async def _review_design(self, payload: dict[str, Any]) -> TaskResult:
        """Review an existing design document."""
        design_doc = payload.get("design", "")
        context = payload.get("context", "")
        focus_areas = payload.get("focus_areas", [])

        focus_text = "\n".join(f"- {area}" for area in focus_areas) if focus_areas else "All aspects"

        prompt = f"""Review the following software design document:

Design Document:
{design_doc}

{f"Context: {context}" if context else ""}

Focus Areas:
{focus_text}

Provide a thorough review covering:
1. Strengths: What works well in this design
2. Weaknesses: Areas that need improvement
3. Scalability: How well it will scale
4. Maintainability: Long-term maintenance considerations
5. Security: Potential security concerns
6. Recommendations: Specific suggestions for improvement"""

        response = await self._call_llm(prompt)

        if response:
            await self._log_discovery(
                category="architecture_review",
                title="Design Review Completed",
                description=f"Reviewed design with focus on: {', '.join(focus_areas) or 'all aspects'}",
                confidence=0.85,
                tags=["design", "review"] + focus_areas,
            )

            return TaskResult(
                success=True,
                result={
                    "review": response,
                    "focus_areas": focus_areas,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to review design",
            )

    async def _create_design(self, payload: dict[str, Any]) -> TaskResult:
        """Create a new architecture design."""
        requirements = payload.get("requirements", "")
        constraints = payload.get("constraints", [])
        tech_stack = payload.get("tech_stack", [])

        constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "None specified"
        tech_text = "\n".join(f"- {t}" for t in tech_stack) if tech_stack else "Open to suggestions"

        prompt = f"""Create a software architecture design for the following requirements:

Requirements:
{requirements}

Constraints:
{constraints_text}

Technology Stack Preferences:
{tech_text}

Provide a comprehensive design document including:
1. Overview: High-level system description
2. Components: Major system components and their responsibilities
3. Data Flow: How data moves through the system
4. Interfaces: API and integration points
5. Data Model: Key entities and relationships
6. Technology Choices: Recommended technologies with rationale
7. Deployment Architecture: How the system will be deployed
8. Scalability Strategy: How to scale the system
9. Security Considerations: Security measures and practices"""

        response = await self._call_llm(prompt)

        if response:
            await self._log_decision(
                decision_type="architecture_design",
                context=f"Created design for: {requirements[:100]}...",
                options_considered=None,
                chosen_option="new_design",
                rationale="Generated based on provided requirements and constraints",
            )

            return TaskResult(
                success=True,
                result={
                    "design": response,
                    "requirements_summary": requirements[:200],
                },
                artifacts=[{
                    "name": "architecture_design",
                    "type": "document",
                    "format": "markdown",
                }],
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to create design",
            )

    async def _review_code(self, payload: dict[str, Any]) -> TaskResult:
        """Review code from an architectural perspective."""
        code = payload.get("code", "")
        language = payload.get("language", "python")
        review_type = payload.get("review_type", "comprehensive")

        prompt = f"""Review the following {language} code from an architectural perspective.

Code:
```{language}
{code}
```

Review Type: {review_type}

Provide a code review covering:
1. Design Patterns: Patterns used and suggestions for improvement
2. SOLID Principles: Adherence to SOLID principles
3. Code Organization: Structure and organization quality
4. Coupling & Cohesion: Analysis of dependencies
5. Testability: How testable the code is
6. Performance: Potential performance concerns
7. Specific Improvements: Concrete suggestions with examples"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "review": response,
                    "language": language,
                    "review_type": review_type,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to review code",
            )

    async def _recommend_refactoring(self, payload: dict[str, Any]) -> TaskResult:
        """Recommend refactoring strategies."""
        code = payload.get("code", "")
        issues = payload.get("issues", [])
        goals = payload.get("goals", ["improve maintainability"])
        language = payload.get("language", "python")

        issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "None specified"
        goals_text = "\n".join(f"- {goal}" for goal in goals)

        prompt = f"""Analyze the following {language} code and recommend refactoring strategies.

Code:
```{language}
{code}
```

Known Issues:
{issues_text}

Refactoring Goals:
{goals_text}

Provide:
1. Current State Analysis: Assessment of the current code
2. Refactoring Opportunities: Specific areas that can be improved
3. Recommended Approach: Step-by-step refactoring plan
4. Design Patterns: Applicable design patterns
5. Example Code: Before/after examples for key changes
6. Risk Assessment: Potential risks and mitigation strategies"""

        response = await self._call_llm(prompt)

        if response:
            return TaskResult(
                success=True,
                result={
                    "recommendations": response,
                    "goals": goals,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to generate refactoring recommendations",
            )

    async def _analyze_decision(self, payload: dict[str, Any]) -> TaskResult:
        """Analyze a technical decision."""
        decision = payload.get("decision", "")
        options = payload.get("options", [])
        criteria = payload.get("criteria", [])
        context = payload.get("context", "")

        options_text = "\n".join(f"- {opt}" for opt in options) if options else "None specified"
        criteria_text = "\n".join(f"- {c}" for c in criteria) if criteria else "Standard criteria"

        prompt = f"""Analyze the following technical decision:

Decision: {decision}

{f"Context: {context}" if context else ""}

Options to Consider:
{options_text}

Evaluation Criteria:
{criteria_text}

Provide a decision analysis including:
1. Problem Statement: Clear definition of the decision to be made
2. Options Analysis: Pros and cons of each option
3. Criteria Evaluation: How each option scores against criteria
4. Recommendation: Suggested choice with rationale
5. Implementation Considerations: What to consider when implementing
6. Reversibility: How easy it is to change this decision later"""

        response = await self._call_llm(prompt)

        if response:
            await self._log_decision(
                decision_type="technical_analysis",
                context=decision,
                options_considered=[{"option": opt} for opt in options],
                chosen_option="analysis_provided",
                rationale="Multi-criteria analysis performed",
            )

            return TaskResult(
                success=True,
                result={
                    "analysis": response,
                    "decision": decision,
                    "options": options,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to analyze decision",
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
