"""
Infra Agent - Handles infrastructure and deployment tasks.

This agent specializes in infrastructure management, deployment,
monitoring setup, and DevOps automation.
"""

import asyncio
from typing import Any

import anthropic

from ..config import get_settings
from ..core.agent_base import BaseAgent, TaskResult
from ..services.rabbitmq_client import TaskMessage


class InfraAgent(BaseAgent):
    """
    Agent specialized in infrastructure and deployment.

    Capabilities:
    - Docker/Kubernetes management
    - Deployment automation
    - Infrastructure provisioning
    - Monitoring setup
    - CI/CD configuration
    """

    AGENT_TYPE = "infra"
    CAPABILITIES = [
        "task.assign",
        "infra.deploy",
        "infra.provision",
        "infra.monitor",
        "docker.manage",
        "k8s.manage",
        "cicd.configure",
    ]

    def __init__(self, **kwargs):
        """Initialize the Infra agent."""
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
        Execute an infrastructure task.

        Args:
            message: Task message with action and payload

        Returns:
            TaskResult with infrastructure status or error
        """
        action = message.action
        payload = message.payload

        self.logger.info(f"Executing action: {action}")

        if action == "task.assign":
            return await self._handle_generic_task(payload)
        elif action == "infra.deploy":
            return await self._deploy_service(payload)
        elif action == "infra.provision":
            return await self._provision_infrastructure(payload)
        elif action == "infra.monitor":
            return await self._setup_monitoring(payload)
        elif action == "docker.manage":
            return await self._manage_docker(payload)
        elif action == "k8s.manage":
            return await self._manage_kubernetes(payload)
        elif action == "cicd.configure":
            return await self._configure_cicd(payload)
        else:
            return TaskResult(
                success=False,
                error=f"Unknown action: {action}",
            )

    async def _handle_generic_task(self, payload: dict[str, Any]) -> TaskResult:
        """Handle a generic infrastructure task."""
        title = payload.get("title", "")
        description = payload.get("description", "")

        prompt = f"""You are a DevOps/Infrastructure engineer. Analyze the following task
and provide a comprehensive infrastructure solution.

Task: {title}

Description: {description}

Provide your response in the following format:
1. Infrastructure Requirements: What infrastructure is needed
2. Implementation Plan: Step-by-step implementation approach
3. Configuration: Required configuration files/settings
4. Security Considerations: Security measures to implement
5. Monitoring: How to monitor the infrastructure
6. Rollback Plan: How to rollback if issues occur"""

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

    async def _deploy_service(self, payload: dict[str, Any]) -> TaskResult:
        """Deploy a service."""
        service_name = payload.get("service", "")
        environment = payload.get("environment", "development")
        version = payload.get("version", "latest")
        config = payload.get("config", {})

        self.logger.info(f"Deploying {service_name} v{version} to {environment}")

        # Generate deployment configuration
        prompt = f"""Generate deployment configuration for the following service:

Service: {service_name}
Environment: {environment}
Version: {version}
Configuration: {config}

Provide:
1. Deployment manifest (Docker Compose or Kubernetes)
2. Environment variables
3. Health check configuration
4. Resource limits
5. Deployment commands"""

        deployment_config = await self._call_llm(prompt)

        if deployment_config:
            await self._log_decision(
                decision_type="deployment",
                context=f"Deploying {service_name}",
                options_considered=[
                    {"option": environment, "rationale": f"Target environment for v{version}"},
                ],
                chosen_option=environment,
                rationale=f"Deploying version {version} to {environment}",
            )

            return TaskResult(
                success=True,
                result={
                    "deployment_config": deployment_config,
                    "service": service_name,
                    "environment": environment,
                    "version": version,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to generate deployment configuration",
            )

    async def _provision_infrastructure(self, payload: dict[str, Any]) -> TaskResult:
        """Provision infrastructure resources."""
        resource_type = payload.get("resource_type", "")
        provider = payload.get("provider", "docker")
        specifications = payload.get("specifications", {})

        prompt = f"""Generate infrastructure provisioning configuration:

Resource Type: {resource_type}
Provider: {provider}
Specifications: {specifications}

Provide:
1. Infrastructure as Code (Terraform/CloudFormation/Docker Compose as appropriate)
2. Resource configuration details
3. Networking setup
4. Security groups/firewall rules
5. Provisioning commands
6. Verification steps"""

        config = await self._call_llm(prompt)

        if config:
            await self._log_discovery(
                category="infrastructure",
                title=f"Provisioned {resource_type}",
                description=f"Created {resource_type} configuration for {provider}",
                confidence=0.85,
                tags=["infrastructure", provider, resource_type],
            )

            return TaskResult(
                success=True,
                result={
                    "infrastructure_config": config,
                    "resource_type": resource_type,
                    "provider": provider,
                },
                artifacts=[{
                    "name": "infrastructure_config",
                    "type": "configuration",
                    "provider": provider,
                }],
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to provision infrastructure",
            )

    async def _setup_monitoring(self, payload: dict[str, Any]) -> TaskResult:
        """Set up monitoring for a service."""
        service_name = payload.get("service", "")
        monitoring_type = payload.get("type", "comprehensive")
        metrics = payload.get("metrics", [])
        alerts = payload.get("alerts", [])

        metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "Standard metrics"
        alerts_text = "\n".join(f"- {a}" for a in alerts) if alerts else "Standard alerts"

        prompt = f"""Set up monitoring for the following service:

Service: {service_name}
Monitoring Type: {monitoring_type}

Metrics to Monitor:
{metrics_text}

Alerts to Configure:
{alerts_text}

Provide:
1. Monitoring stack configuration (Prometheus/Grafana)
2. Metric collection configuration
3. Dashboard configuration
4. Alert rules
5. Notification channels setup
6. Health check endpoints"""

        config = await self._call_llm(prompt)

        if config:
            return TaskResult(
                success=True,
                result={
                    "monitoring_config": config,
                    "service": service_name,
                    "monitoring_type": monitoring_type,
                },
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to setup monitoring",
            )

    async def _manage_docker(self, payload: dict[str, Any]) -> TaskResult:
        """Manage Docker containers/images."""
        operation = payload.get("operation", "status")
        target = payload.get("target", "")
        options = payload.get("options", {})

        if operation == "status":
            # Get Docker status
            try:
                process = await asyncio.create_subprocess_shell(
                    "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                return TaskResult(
                    success=process.returncode == 0,
                    result={
                        "output": stdout.decode() if stdout else "",
                        "operation": operation,
                    },
                )
            except Exception as e:
                return TaskResult(
                    success=False,
                    error=f"Failed to get Docker status: {str(e)}",
                )

        elif operation == "build":
            # Generate Dockerfile
            prompt = f"""Generate a Dockerfile for the following specifications:

Target: {target}
Options: {options}

Provide:
1. Optimized Dockerfile
2. .dockerignore file
3. Build instructions
4. Multi-stage build if appropriate"""

            dockerfile = await self._call_llm(prompt)

            return TaskResult(
                success=True if dockerfile else False,
                result={
                    "dockerfile": dockerfile,
                    "operation": operation,
                },
                error=None if dockerfile else "Failed to generate Dockerfile",
            )

        elif operation == "compose":
            # Generate Docker Compose
            prompt = f"""Generate a Docker Compose configuration for:

Target: {target}
Options: {options}

Provide:
1. docker-compose.yml
2. Environment file template
3. Volume configurations
4. Network setup"""

            compose_config = await self._call_llm(prompt)

            return TaskResult(
                success=True if compose_config else False,
                result={
                    "compose_config": compose_config,
                    "operation": operation,
                },
                error=None if compose_config else "Failed to generate Docker Compose",
            )

        else:
            return TaskResult(
                success=False,
                error=f"Unknown Docker operation: {operation}",
            )

    async def _manage_kubernetes(self, payload: dict[str, Any]) -> TaskResult:
        """Manage Kubernetes resources."""
        operation = payload.get("operation", "status")
        resource_type = payload.get("resource_type", "deployment")
        namespace = payload.get("namespace", "default")
        specifications = payload.get("specifications", {})

        if operation == "status":
            try:
                process = await asyncio.create_subprocess_shell(
                    f"kubectl get {resource_type} -n {namespace}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                return TaskResult(
                    success=process.returncode == 0,
                    result={
                        "output": stdout.decode() if stdout else "",
                        "errors": stderr.decode() if stderr else "",
                        "operation": operation,
                    },
                )
            except Exception as e:
                return TaskResult(
                    success=False,
                    error=f"Failed to get Kubernetes status: {str(e)}",
                )

        elif operation == "generate":
            prompt = f"""Generate Kubernetes manifests for:

Resource Type: {resource_type}
Namespace: {namespace}
Specifications: {specifications}

Provide:
1. Deployment manifest
2. Service manifest
3. ConfigMap/Secret templates
4. Horizontal Pod Autoscaler (if appropriate)
5. Resource limits and requests"""

            manifests = await self._call_llm(prompt)

            return TaskResult(
                success=True if manifests else False,
                result={
                    "manifests": manifests,
                    "resource_type": resource_type,
                    "namespace": namespace,
                },
                error=None if manifests else "Failed to generate Kubernetes manifests",
            )

        else:
            return TaskResult(
                success=False,
                error=f"Unknown Kubernetes operation: {operation}",
            )

    async def _configure_cicd(self, payload: dict[str, Any]) -> TaskResult:
        """Configure CI/CD pipeline."""
        platform = payload.get("platform", "github_actions")
        project_type = payload.get("project_type", "python")
        stages = payload.get("stages", ["build", "test", "deploy"])

        stages_text = "\n".join(f"- {s}" for s in stages)

        prompt = f"""Generate CI/CD pipeline configuration:

Platform: {platform}
Project Type: {project_type}

Required Stages:
{stages_text}

Provide:
1. Pipeline configuration file (YAML)
2. Environment setup
3. Secret management approach
4. Caching strategy
5. Deployment triggers
6. Notification setup"""

        config = await self._call_llm(prompt)

        if config:
            await self._log_discovery(
                category="cicd",
                title=f"CI/CD configuration for {platform}",
                description=f"Created {project_type} pipeline with stages: {', '.join(stages)}",
                confidence=0.85,
                tags=["cicd", platform, project_type],
            )

            return TaskResult(
                success=True,
                result={
                    "cicd_config": config,
                    "platform": platform,
                    "project_type": project_type,
                    "stages": stages,
                },
                artifacts=[{
                    "name": "cicd_config",
                    "type": "configuration",
                    "platform": platform,
                }],
            )
        else:
            return TaskResult(
                success=False,
                error="Failed to configure CI/CD",
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
