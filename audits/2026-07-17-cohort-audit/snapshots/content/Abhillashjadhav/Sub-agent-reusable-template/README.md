# Reusable Sub-Agent Template Architecture

A comprehensive, modular architecture for building applications using specialized AI sub-agents. Each agent represents a specific technical role in the software development lifecycle.

## Overview

This repository provides a reusable template system for orchestrating 45 specialized roles as AI sub-agents. Each agent is designed with specific expertise, responsibilities, and capabilities to handle different aspects of application development.

## Architecture Highlights

- **45 Specialized Roles**: Including leadership, design, frontend, backend, AI/ML, infrastructure, QA, and specialized functions
- **Modular Design**: Each agent can work independently or collaboratively
- **Reusable Templates**: Easy to instantiate and customize agents for specific projects
- **Workflow Orchestration**: Pre-defined workflows for common development tasks
- **Configuration-Based**: JSON-based agent definitions for easy customization

## Project Structure

```
.
├── README.md                          # This file
├── ARCHITECTURE.md                    # Detailed architecture documentation
├── ROLES_REFERENCE.md                 # Complete list of all 45 roles
├── agents/                            # Agent role definitions
│   ├── leadership/                    # Leadership & Management agents
│   ├── design/                        # Design & UX agents
│   ├── frontend/                      # Frontend development agents
│   ├── backend/                       # Backend development agents
│   ├── data-ai/                       # Data & AI/ML agents
│   ├── infrastructure/                # Infrastructure & DevOps agents
│   ├── quality/                       # QA & Testing agents
│   └── specialized/                   # Specialized technical agents
├── workflows/                         # Orchestrated workflows
│   ├── feature-development.json       # End-to-end feature development
│   ├── bug-fix.json                   # Bug fixing workflow
│   ├── architecture-review.json       # Architecture validation
│   └── deployment.json                # Deployment workflow
├── templates/                         # Reusable templates
│   ├── agent-template.json            # Base agent template
│   └── workflow-template.json         # Base workflow template
└── examples/                          # Usage examples
    ├── simple-crud-app.md             # Simple CRUD app example
    └── microservices-app.md           # Microservices app example
```

## Agent Categories

### 1. Leadership & Management (2 agents)
- Orchestrator/CEO Agent
- Product Manager Agent

### 2. Design & User Experience (4 agents)
- UI/UX Designer
- Design Systems Architect
- Interaction Designer
- Accessibility Specialist

### 3. Frontend Development (6 agents)
- Frontend Architect
- Web Frontend Developer
- Mobile Frontend Developer
- iOS Developer
- Android Developer
- Frontend Performance Engineer

### 4. Backend Development (7 agents)
- Backend Architect
- Solutions Architect
- API Developer
- Microservices Engineer
- Backend Developer
- Integration Engineer
- Serverless Engineer

### 5. Data & AI/ML (6 agents)
- Data Architect
- Database Engineer
- Data Engineer
- ML/AI Engineer
- Data Scientist
- ML Infrastructure Engineer

### 6. Infrastructure & DevOps (7 agents)
- DevOps Engineer
- Cloud Architect
- Platform Engineer
- Site Reliability Engineer (SRE)
- Security Engineer
- Network Engineer
- Container/Kubernetes Engineer

### 7. Quality Assurance & Testing (5 agents)
- QA Engineer
- Test Automation Engineer
- Performance Testing Engineer
- Security Testing Engineer
- Chaos Engineer

### 8. Specialized Technical Roles (8 agents)
- Technical Lead
- Code Quality Engineer
- Documentation Engineer
- Release Manager
- Observability Engineer
- Cost Optimization Engineer
- Compliance Engineer
- Developer Experience Engineer

## Quick Start

### 1. Using a Single Agent

```bash
# Load an agent configuration
agent=$(cat agents/backend/solutions-architect.json)

# Invoke the agent with a task
./invoke-agent.sh solutions-architect "Review the proposed microservices architecture"
```

### 2. Using a Workflow

```bash
# Run a complete feature development workflow
./run-workflow.sh feature-development --feature "user authentication"
```

### 3. Creating a Custom Agent

```bash
# Copy the template
cp templates/agent-template.json agents/custom/my-agent.json

# Edit the configuration
vim agents/custom/my-agent.json

# Test the agent
./test-agent.sh custom/my-agent
```

## Key Features

### Modular Architecture
Each agent is self-contained with:
- Clear responsibilities
- Required skills and tools
- Input/output specifications
- Collaboration interfaces

### Intelligent Orchestration
Workflows automatically:
- Determine which agents to invoke
- Manage dependencies between agents
- Handle parallel and sequential execution
- Aggregate and validate results

### Extensible Design
Easily extend with:
- New agent roles
- Custom workflows
- Domain-specific agents
- Industry-specific templates

## Common Use Cases

1. **Feature Development**: UI/UX Designer → Frontend Developer → Backend Developer → QA Engineer
2. **Architecture Review**: Solutions Architect → Security Engineer → Performance Engineer
3. **Bug Fix**: Code Quality Engineer → Backend/Frontend Developer → Test Automation Engineer
4. **ML Model Deployment**: ML Engineer → ML Infrastructure Engineer → DevOps Engineer → SRE
5. **Performance Optimization**: Performance Testing Engineer → Frontend Performance Engineer → Cloud Architect

## Agent Communication Protocol

Agents communicate through a standardized protocol:

```json
{
  "from": "frontend-architect",
  "to": "backend-architect",
  "type": "request",
  "payload": {
    "action": "design_api",
    "data": { "endpoints": [...] }
  }
}
```

## Configuration

Each agent is configured with:
- **Identity**: Name, role, specialization
- **Capabilities**: Skills, tools, frameworks
- **Responsibilities**: Primary and secondary duties
- **Dependencies**: Required input from other agents
- **Outputs**: Deliverables and artifacts
- **Prompts**: Role-specific instructions and context

## Contributing

To add a new agent role:
1. Copy `templates/agent-template.json`
2. Fill in the agent configuration
3. Add to appropriate category folder
4. Update this README and ROLES_REFERENCE.md
5. Create usage examples

## License

MIT License - See LICENSE file for details

## Version

**v1.0.0** - Initial comprehensive architecture with 45 specialized roles (including Leadership & Management)
