"""
Coder Agent - Generates and modifies code.

This agent handles code generation, bug fixing, refactoring,
and other code-related tasks.
"""

from typing import Any

import anthropic

from ..config import get_settings
from ..core.agent_base import BaseAgent, TaskResult
from ..services.rabbitmq_client import TaskMessage
from ..utils import get_logger


class CoderAgent(BaseAgent):
    """
    Agent specialized in code generation and modification.

    Capabilities:
    - Code generation from specifications
    - Bug fixing
    - Refactoring
    - Documentation generation
    """

    AGENT_TYPE = "coder"
    CAPABILITIES = [
        "task.assign",
        "code.generate",
        "code.fix",
        "code.refactor",
        "code.document",
    ]

    def __init__(self, **kwargs):
        """Initialize the Coder agent."""
        super().__init__(**kwargs)
        self._settings = get_settings()
        self._anthropic: anthropic.AsyncAnthropic | None = None

    async def start(self) -> None:
        """Start the agent and initialize LLM client."""
        await super().start()

        # Initialize Anthropic client
        api_key = self._settings.llm.api_key
        if api_key:
            self._anthropic = anthropic.AsyncAnthropic(api_key=api_key)
            self.logger.info("Anthropic client initialized")
        else:
            self.logger.warning("No API key configured - LLM calls will fail")

    async def execute_task(self, message: TaskMessage) -> TaskResult:
        """
        Execute a coding task.

        Args:
            message: Task message with action and payload

        Returns:
            TaskResult with generated code or error
        """
        action = message.action
        payload = message.payload

        self.logger.info(f"Executing action: {action}")

        if action == "task.assign":
            # Generic task assignment - analyze and execute
            return await self._handle_generic_task(payload)
        elif action == "code.generate":
            return await self._generate_code(payload)
        elif action == "code.fix":
            return await self._fix_code(payload)
        elif action == "code.refactor":
            return await self._refactor_code(payload)
        elif action == "code.document":
            return await self._document_code(payload)
        else:
            return TaskResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _handle_generic_task(self, payload: dict[str, Any]) -> TaskResult:
        """Handle a generic task assignment."""
        title = payload.get("title", "")
        description = payload.get("description", "")

        # Use LLM to understand and execute the task
        prompt = f"""You are a coding assistant. Analyze the following task and provide a solution.

Task: {title}

Description: {description}

Provide your response in the following format:
1. Analysis: Brief analysis of what needs to be done
2. Solution: The code or steps to accomplish the task
3. Explanation: Explanation of the solution

If code is required, provide complete, working code."""

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

    async def _generate_code(self, payload: dict[str, Any]) -> TaskResult:
        """Generate code based on specification."""
        specification = payload.get("specification", "")
        language = payload.get("language", "python")
        context = payload.get("context", "")

        prompt = f"""Generate {language} code based on the following specification:

Specification:
{specification}

{f"Context: {context}" if context else ""}

Requirements:
- Write clean, well-documented code
- Follow best practices for {language}
- Include error handling where appropriate
- Add type hints if using Python

Provide only the code, no explanations."""

        code = await self._call_llm(prompt)

        if code:
            # Log discovery about the generated code
            await self._log_discovery(
                category="codebase_pattern",
                title=f"Generated {language} code",
                description=f"Generated code for: {specification[:100]}...",
                confidence=0.8,
                tags=[language, "generated"],
            )

            return TaskResult(
                success=True,
                result={
                    "code": code,
                    "language": language,
                },
                artifacts=[{
                    "name": "generated_code",
                    "type": "code",
                    "language": language,
                }],
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to generate code",
            )

    async def _fix_code(self, payload: dict[str, Any]) -> TaskResult:
        """Fix bugs in provided code."""
        code = payload.get("code", "")
        error_message = payload.get("error", "")
        language = payload.get("language", "python")

        prompt = f"""Fix the following {language} code that has a bug:

Code:
```{language}
{code}
```

Error message:
{error_message}

Provide the fixed code with comments explaining what was wrong and how it was fixed."""

        fixed_code = await self._call_llm(prompt)

        if fixed_code:
            return TaskResult(
                success=True,
                result={
                    "fixed_code": fixed_code,
                    "original_error": error_message,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to fix code",
            )

    async def _refactor_code(self, payload: dict[str, Any]) -> TaskResult:
        """Refactor code for better quality."""
        code = payload.get("code", "")
        goals = payload.get("goals", ["improve readability", "reduce complexity"])
        language = payload.get("language", "python")

        goals_text = "\n".join(f"- {goal}" for goal in goals)

        prompt = f"""Refactor the following {language} code with these goals:

{goals_text}

Code:
```{language}
{code}
```

Provide the refactored code with comments explaining the improvements made."""

        refactored = await self._call_llm(prompt)

        if refactored:
            return TaskResult(
                success=True,
                result={
                    "refactored_code": refactored,
                    "goals": goals,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to refactor code",
            )

    async def _document_code(self, payload: dict[str, Any]) -> TaskResult:
        """Generate documentation for code."""
        code = payload.get("code", "")
        doc_type = payload.get("doc_type", "docstrings")
        language = payload.get("language", "python")

        prompt = f"""Add comprehensive {doc_type} to the following {language} code:

```{language}
{code}
```

Requirements:
- Add docstrings to all functions/classes
- Include parameter descriptions
- Include return value descriptions
- Add usage examples where helpful

Provide the code with added documentation."""

        documented = await self._call_llm(prompt)

        if documented:
            return TaskResult(
                success=True,
                result={
                    "documented_code": documented,
                    "doc_type": doc_type,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to document code",
            )

    async def _call_llm(self, prompt: str) -> str | None:
        """
        Call the LLM API with a prompt.

        Args:
            prompt: The prompt to send

        Returns:
            The LLM response text or None on error
        """
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
