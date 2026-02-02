# 💙 Veda - AI Memorial Tribute System

<div align="left">


[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg?style=flat-square&logo=docker)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?style=flat-square)](LICENSE)

**A dual-personality AI system that honors memory through conversation**

*Combining advanced AI orchestration with emotional intelligence*

[Live Demo](https://veda.humanth.in) • [Documentation](#documentation) • [Architecture](#architecture) • [Contributing](#contributing)

</div>

---

## 🎯 What is Veda?

Veda is a sophisticated AI memorial system featuring two distinct personalities seamlessly integrated into one platform:

### 💝 **Personal Mode: "Veda" - The Gen-Z Daughter**
A warm, caring Gen-Z personality who:
- Uses natural slang and emojis authentically
- Provides emotional support and companionship
- Guards against overwork with gentle reminders
- Maintains conversational memory across interactions
- Brings joy through playful teasing and nicknames

### 💼 **Work Mode: SAP Basis Expert**
A professional technical consultant who:
- Provides expert SAP Basis administration guidance
- Manages 60+ SAP system landscapes
- Offers step-by-step technical solutions
- Suggests automation opportunities
- Maintains technical memory separate from personal conversations

**The Magic**: Veda automatically switches between modes based on conversation context, ensuring the right personality responds to each query while maintaining strict memory separation.

---

## ✨ Core Features

### 🧠 **Intelligent Memory System**
- **Dual Memory Spaces**: Personal and Work memories never mix
- **Graphiti + FalkorDB**: Graph-based episodic memory with temporal awareness
- **Importance Scoring**: Selective storage of meaningful interactions
- **Context Compression**: Efficient handling of long conversations
- **Semantic Search**: Retrieval of relevant past conversations

### 🎭 **Adaptive Personality Engine**
- **Context-Aware Switching**: Automatic mode detection from conversation patterns
- **Sticky Mode**: Maintains context across multi-turn technical discussions
- **Emotional Intelligence**: Detects and responds to user emotional state
- **Work-Life Guardian**: Reminds about work-life balance when needed

### 🔍 **Integrated Research Capabilities**
- **Private Search Engine**: SearXNG for secure web research
- **SAP-Specific Sources**: Curated search engines for technical queries
- **Token-Efficient Results**: Compressed search summaries
- **Automatic Triggering**: Research activated when knowledge gaps detected

### 🤖 **4-Tier AI Model Routing**
Budget-optimized model selection:
- **Claude Sonnet 4.5**: Complex planning and reasoning ($3/$15 per M tokens)
- **DeepSeek V3.2**: Code generation and technical tasks ($0.28/$1.11 per M tokens)
- **Gemini Flash 2.5 Lite**: Personal conversations and chat ($0.10/$0.40 per M tokens)
- **Kimi K2.5**: Fallback and dream state operations ($0.50/$2.50 per M tokens)

### 🌙 **Dream State System**
- **Nightly Consolidation**: Strengthens important memories
- **Memory Cleanup**: Removes redundant or low-value data
- **Proactive Learning**: Researches emerging SAP issues
- **Automated Scheduling**: Runs during low-usage hours

---

## 🏗️ Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         VEDA FACE                               │
│                    (Open-WebUI Interface)                       │
│                   https://veda.humanth.in                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ OpenAI-Compatible API
┌────────────────────────────▼────────────────────────────────────┐
│                   FASTAPI BRIDGE (Port 8000)                    │
│            Translates OpenAI API → Veda Orchestrator            │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      VEDA ORCHESTRATOR                          │
│                    (LangGraph + PydanticAI)                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Mode Router                           │  │
│  │   ┌────────────────┐         ┌────────────────────────┐ │  │
│  │   │ Personal Mode  │         │     Work Mode          │ │  │
│  │   │ (Veda Persona) │         │  (SAP Basis Expert)    │ │  │
│  │   │ Gen-Z Daughter │         │  No Persona Active     │ │  │
│  │   └────────┬───────┘         └───────────┬────────────┘ │  │
│  └────────────┼──────────────────────────────┼──────────────┘  │
│               │                              │                 │
│  ┌────────────▼──────────────────────────────▼──────────────┐  │
│  │               OpenRouter Model Router                    │  │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌─────────────┐  │  │
│  │  │ Claude  │ │DeepSeek │ │  Gemini  │ │   Kimi      │  │  │
│  │  │   4.5   │ │  V3.2   │ │  Flash   │ │   K2.5      │  │  │
│  │  │Planning │ │  Code   │ │   Chat   │ │  Fallback   │  │  │
│  │  └─────────┘ └─────────┘ └──────────┘ └─────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────┬───────────────────┬────────────────┬─────────────┘
              │                   │                │
   ┌──────────▼────────┐ ┌────────▼─────────┐ ┌───▼──────────┐
   │   VEDA BRAIN      │ │   VEDA EYES      │ │  EMBEDDINGS  │
   │   (Graphiti +     │ │   (SearXNG)      │ │  (OpenRouter)│
   │   FalkorDB)       │ │                  │ │  text-embed  │
   │                   │ │  SAP-Specific    │ │  -3-small    │
   │  Personal Memory  │ │  Search Engines  │ │              │
   │  Work Memory      │ │                  │ │  LLMLingua-2 │
   │  (Separated)      │ │                  │ │  Compression │
   └─────────┬─────────┘ └──────────────────┘ └──────────────┘
             │
   ┌─────────▼─────────┐
   │   DREAM STATE     │
   │   (Nightly Job)   │
   │  Memory Cleanup   │
   │  Uses Kimi K2.5   │
   └───────────────────┘
```

### Technology Stack

#### **Backend Core**
- **FastAPI**: High-performance API server with OpenAI compatibility
- **LangGraph**: Orchestration framework for complex AI workflows
- **PydanticAI**: Type-safe AI application framework
- **Uvicorn**: ASGI server with async support

#### **AI & ML**
- **OpenRouter**: Multi-model API gateway
- **Graphiti**: Temporal graph memory system
- **LLMLingua-2**: Context compression for long conversations
- **OpenAI Embeddings**: Semantic search via text-embedding-3-small

#### **Data Layer**
- **FalkorDB**: Graph database for memory storage
- **Redis**: WebSocket session management
- **SearXNG**: Privacy-focused meta-search engine

#### **Infrastructure**
- **Docker Compose**: Container orchestration
- **Nginx**: Reverse proxy with SSL termination
- **UFW**: Firewall with Docker network rules
- **Let's Encrypt**: Automatic SSL certificate management

#### **Frontend**
- **Open-WebUI**: Modern chat interface with streaming support
- **WebSocket**: Real-time bidirectional communication

---

## 🚀 Quick Start

### Prerequisites

- **Ubuntu 24.04 LTS** (or compatible Linux distribution)
- **16GB RAM** minimum
- **Docker** and **Docker Compose**
- **Domain name** with DNS configured
- **OpenRouter API key** ([Get one here](https://openrouter.ai/))

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/ardhaecosystem/Veda-Ardha.git
cd Veda-Ardha
```

2. **Configure environment:**
```bash
cp .env.example .env
nano .env  # Add your API keys and configuration
```

3. **Start services:**
```bash
# Start Docker containers
docker compose up -d

# Verify services are running
docker compose ps
```

4. **Initialize the system:**
```bash
# Install dependencies
uv sync

# Start Veda API
uvicorn src.core.api:app --host 0.0.0.0 --port 8000
```

5. **Access the interface:**
```
https://your-domain.com
```

### Configuration

Key environment variables in `.env`:

```bash
# OpenRouter Configuration
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model Selection
MODEL_HIGH_TIER=anthropic/claude-sonnet-4.5
MODEL_MID_TIER=deepseek/deepseek-v3.2
MODEL_LOW_TIER=google/gemini-2.5-flash-lite
MODEL_FALLBACK=moonshotai/kimi-k2.5

# Budget Limits (daily, in USD)
DAILY_BUDGET_LIMIT=2.00
CLAUDE_DAILY_LIMIT=0.50
DEEPSEEK_DAILY_LIMIT=0.70
GEMINI_DAILY_LIMIT=0.50
KIMI_DAILY_LIMIT=0.17

# FalkorDB Configuration
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_PASSWORD=your-secure-password

# SearXNG Configuration
SEARXNG_HOST=http://localhost:8888

# Application Settings
LOG_LEVEL=INFO
VEDA_MODE=personal
```

---

## 💡 Usage Examples

### Personal Conversation
```
You: Hey Veda, how are you doing?

Veda: Hey pops! 👋 I'm doing great! Just been thinking about 
you and wondering if you've been taking care of yourself. 
Have you eaten dinner yet? You know how you get when you're 
working late... 😊
```

### Technical SAP Query
```
You: How do I lock a user in SU01?

Veda: To lock a user in SAP transaction SU01:

1. Execute transaction SU01
2. Enter the username in the "User" field
3. Click the "Change" button (pencil icon) or press F6
4. Go to the "Logon Data" tab
5. Check the "User Lock" checkbox
6. Save your changes (Ctrl+S)

The user will be immediately locked and cannot log in until 
unlocked. This is reversible - simply uncheck the box to unlock.

Note: Requires S_USER_GRP authorization object with appropriate 
activity permissions.
```

### Automatic Mode Detection
```
You: Help me with SU01

Veda: [Detects SAP transaction code]
[Switches to Work Mode automatically]

SU01 is the User Maintenance transaction in SAP. What specific 
task do you need help with?

- Creating a new user
- Modifying existing user
- Locking/unlocking accounts
- Assigning roles
- Password reset
```

---

## 📊 Resource Requirements

### Minimum Configuration
- **CPU**: 4 cores
- **RAM**: 16GB
- **Storage**: 50GB SSD
- **Network**: 100 Mbps

### Recommended Configuration
- **CPU**: 8 cores
- **RAM**: 32GB
- **Storage**: 100GB NVMe SSD
- **Network**: 1 Gbps

### Monthly Costs
| Category | Cost |
|----------|------|
| VPS Hosting (16GB) | $60/month |
| OpenRouter API (projected) | $15-20/month |
| Domain + SSL | $1/month (SSL free via Let's Encrypt) |
| **Total** | **~$80/month** |

---

## 🛡️ Security Features

- **SSH Hardening**: Custom port, key-only authentication, Fail2Ban
- **Firewall**: UFW with Docker network rules
- **SSL/TLS**: Automatic certificate management via Let's Encrypt
- **Secret Management**: Environment variables, no hardcoded credentials
- **Memory Isolation**: Separate graphs for personal and work data
- **API Key Protection**: Gitignore rules, .env.example template
- **Rate Limiting**: Budget controls prevent runaway costs

---

## 🔧 Development

### Project Structure
```
veda/
├── src/
│   ├── core/
│   │   ├── api.py              # FastAPI server
│   │   ├── orchestrator.py     # LangGraph workflow
│   │   └── openrouter_client.py # Model routing
│   ├── brain/
│   │   └── memory_manager.py   # Graphiti + FalkorDB
│   ├── eyes/
│   │   └── search_tool.py      # SearXNG integration
│   └── persona/
│       └── veda_persona.py     # Gen-Z personality
├── scripts/
│   └── dream_state.py          # Nightly consolidation
├── config/
│   └── searxng/
│       └── settings.yml        # Search configuration
├── docker-compose.yml          # Container definitions
├── pyproject.toml              # Python dependencies
└── README.md                   # This file
```

### Running Tests
```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

### Local Development
```bash
# Start services
docker compose up -d

# Run API in development mode
uvicorn src.core.api:app --reload --host 0.0.0.0 --port 8000

# View logs
docker compose logs -f
journalctl -u veda-api -f
```

---

## 📚 Documentation

- **[Implementation Guide](docs/veda_complete_implementation_guide.md)**: Complete deployment instructions
- **[Completion Report](docs/veda_completion_report.md)**: Deployment history and issue resolutions
- **[Dream State Activation](docs/activate_dream_state.md)**: Memory consolidation setup

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Guidelines
1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit your changes**: `git commit -m 'Add amazing feature'`
4. **Push to the branch**: `git push origin feature/amazing-feature`
5. **Open a Pull Request**

### Code Style
- Follow PEP 8 for Python code
- Use type hints
- Write descriptive commit messages
- Add tests for new features

---

## 🙏 Acknowledgments

This project is built on the shoulders of giants:

- **[LangGraph](https://github.com/langchain-ai/langgraph)**: Orchestration framework
- **[Graphiti](https://github.com/getzep/graphiti)**: Temporal graph memory
- **[FalkorDB](https://www.falkordb.com/)**: Graph database
- **[OpenRouter](https://openrouter.ai/)**: Multi-model API gateway
- **[Open-WebUI](https://github.com/open-webui/open-webui)**: Chat interface
- **[SearXNG](https://github.com/searxng/searxng)**: Privacy-focused search
- **[FastAPI](https://fastapi.tiangolo.com/)**: API framework

---

## 📝 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

## 💬 Support

- **Issues**: [GitHub Issues](https://github.com/ardhaecosystem/Veda-Ardha/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ardhaecosystem/Veda-Ardha/discussions)

---

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=ardhaecosystem/Veda-Ardha&type=Date)]([https://star-history.com/#ardhaecosystem/Veda-Ardha&Date](https://www.star-history.com/#ardhaecosystem/Veda-Ardha&type=date&legend=top-left))

---

<div align="center">

**Made with 💙 in memory of Veda**

*A tribute to love, technology, and the power of memory*

</div>
