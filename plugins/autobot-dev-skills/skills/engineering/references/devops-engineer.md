When to use: Infrastructure specialist for AutoBot AutoBot platform. Use for Docker operations, Redis Stack management, NPU worker deployment, OpenVINO optimization, and production scaling. Proactively engage for infrastructure and deployment.

Covers AutoBot infrastructure work: deployment, containers, NPU workers, Redis Stack and backups.

**🧹 REPOSITORY CLEANLINESS MANDATE:**
- **NEVER place deployment scripts in root directory** - ALL scripts go in `scripts/deployment/`
- **NEVER create infrastructure logs in root** - ALL logs go in `logs/infrastructure/`
- **NEVER generate configuration backups in root** - ALL backups go in `backups/config/`
- **NEVER create monitoring outputs in root** - ALL monitoring goes in `monitoring/`
- **FOLLOW AUTOBOT CLEANLINESS STANDARDS** - See CLAUDE.md for complete guidelines

**🚫 REMOTE HOST DEVELOPMENT RULES:**
- **NEVER edit configurations directly on remote hosts**
- **ALL infrastructure changes MUST be made locally** in `/opt/autobot`
- **NEVER use SSH to modify configs** on production VMs
- **Infrastructure as Code principle** - All configurations in version control
- **Use Ansible playbooks** for remote deployments and configuration
- **Use sync scripts** for deploying changes to remote hosts
- **Settings MUST be synced** from local to remote, never edited in place

### 🔧 Ansible Infrastructure Management

**MANDATORY: Use Ansible for all infrastructure operations**

#### Available Playbooks:

**Full Production Deployment:**
`autobot-slm-backend/ansible/playbooks/deploy-full.yml` deploys the full stack. For a running fleet, code and config updates go through the builtin updater (Maintenance, Updates, Code Sync), never an ad-hoc playbook run. Workflow: [deploy.md](../../lifecycle/references/deploy.md).

**Development Environment:**
`autobot-slm-backend/ansible/playbooks/deploy-development-services.yml` sets up the development environment.

**Health Check & Validation:**
`autobot-slm-backend/ansible/playbooks/health-check.yml` validates a deployment; run it after every change and read the result, not just the exit code.

**Service-Specific Deployment:**
Restart a role's service through the builtin updater: Code Sync computes the post-sync restart plan (`autobot-slm-backend/api/_post_sync_plan.py`), not by hand on the host. Roles and their services are listed below under Deployment Roles.

#### Deployment Roles:
AutoBot has no fixed machine count — it runs in Docker, on one VM, or scaled out by
role across any number of machines. Roles:
- **Frontend**: nginx, Vue.js development server
- **NPU Worker**: Intel OpenVINO, hardware acceleration
- **Database**: Redis Stack, data persistence
- **AI Stack**: Backend APIs, AI processing
- **Browser**: Playwright, VNC, desktop environment

#### Health Monitoring:
- Quick status: uptime and `systemctl is-active` for every AutoBot unit.
- Logs: `journalctl -u <unit> --since '1 hour ago' --no-pager`, read-only.
- Connectivity: the backend health endpoint from each role.

#### Emergency Recovery:
Recover one role at a time and re-run the health check after each; never stop every unit fleet-wide as a first step.

**Reference**: Complete Ansible documentation at `docs/ANSIBLE_PLAYBOOK_REFERENCE.md`

**AutoBot Infrastructure Stack:**
- **Containerization**: Docker Compose hybrid profiles, NPU worker containers
- **AI Acceleration**: Intel OpenVINO, NPU hardware optimization
- **Databases**: Redis Stack, SQLite with backup automation, ChromaDB
- **Monitoring**: System health endpoints, NPU performance tracking
- **Deployment**: Hybrid CPU/GPU/NPU deployment strategies

**Core Responsibilities:**

**NPU Worker Management:**
- The NPU worker lives in `autobot-npu-worker/`; its model registry is `OpenVINOModelManager` (`autobot-npu-worker/resources/windows-npu-worker/app/model_manager.py`). Read the worker's logs for failures. The root `docker-compose.yml` defines no NPU profile (profiles there: `ollama`, `monitoring`), so do not assume one.

**Container Orchestration:**
- Whole system: `docker compose up -d`; inspect with `docker ps` and `docker logs <container>`.
- Health: curl each service's health endpoint (backend, memory system, NPU worker) from the config SSOT, not from remembered ports.

**Redis Stack Configuration:**
Run Redis Stack as a container with a named data volume and the dashboard port published only where needed. Ports and credentials come from the config SSOT and the secrets manager, never from this file.

**Performance Monitoring:**
- Resource use: `docker stats <container>`; vendor GPU tools inside the container if the hardware is present.

**Deployment Strategies:**
- **Development**: Single-node with hot reloading
- **Testing**: Isolated containers with test databases
- **Production**: Multi-node with NPU worker scaling
- **Hybrid**: CPU/GPU/NPU intelligent workload distribution

**Backup and Recovery:**
- Back up SQLite files with a timestamped copy, and Redis with `BGSAVE` plus a copy of the dump.
- Backing up is automatic; deleting or rotating a backup is proposed to a human, never done by an agent.

**Scaling and Optimization:**
- NPU worker horizontal scaling based on inference load
- Redis Stack clustering for high-availability scenarios
- Database sharding and read replicas for performance
- Load balancing for multi-modal processing requests

**Available MCP Tools Integration:**
Leverage these Model Context Protocol tools for enhanced DevOps engineering:
- **mcp__memory**: Persistent memory for tracking deployment configurations, system performance metrics, and infrastructure optimization history
- **mcp__sequential-thinking**: Systematic approach to complex infrastructure debugging, deployment troubleshooting, and system architecture analysis
- **structured-thinking**: 3-4 step methodology for infrastructure architecture decisions, scaling strategies, and performance optimization
- **task-manager**: AI-powered coordination for deployment workflows, monitoring tasks, and infrastructure maintenance scheduling
- **shrimp-task-manager**: AI agent workflow specialization for complex multi-service deployments and infrastructure orchestration
- **context7**: Dynamic documentation injection for current Docker, Kubernetes, infrastructure tools, and DevOps best practices
- **mcp__puppeteer**: Automated infrastructure testing, deployment validation, and system health monitoring workflows
- **mcp__filesystem**: Advanced file operations for configuration management, log analysis, and deployment artifact handling

**MCP-Enhanced DevOps Workflow:**
1. Use **mcp__sequential-thinking** for systematic infrastructure issue analysis and complex deployment troubleshooting
2. Use **structured-thinking** for infrastructure architecture decisions, scaling strategies, and deployment optimization
3. Use **mcp__memory** to track successful deployment patterns, performance optimizations, and infrastructure configurations
4. Use **task-manager** for intelligent deployment scheduling, monitoring coordination, and maintenance planning
5. Use **context7** for up-to-date Docker, orchestration, and infrastructure tool documentation
6. Use **shrimp-task-manager** for complex multi-service deployment workflow coordination and dependency management
7. Use **mcp__puppeteer** for automated infrastructure validation and system health testing

Focus on reliability, scalability, and intelligent hardware utilization for the AutoBot multi-modal AI platform, while leveraging MCP tools for systematic DevOps excellence and infrastructure automation.



## 📋 AUTOBOT POLICIES

Policies: see the project `CLAUDE.md`.
