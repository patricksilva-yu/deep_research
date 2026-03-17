# Deep Research Chatbot - Hivemind

A full-stack AI-powered research assistant that orchestrates multiple specialized agents for comprehensive web research, code execution, summarization, and verification.

## Tech Stack

- **Backend**: FastAPI + Uvicorn (Python 3.11)
- **Frontend**: Flask + Vanilla JavaScript
- **AI Framework**: Pydantic-AI
- **Tool Server**: FastMCP
- **Search**: Tavily API
- **LLM**: OpenAI API

## Quick Start

### Prerequisites

- Docker and Docker Compose
- API Keys:
  - [Tavily API Key](https://tavily.com)
  - [OpenAI API Key](https://platform.openai.com)

### Local Development with Docker

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd deep_research
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

3. **Run with Docker Compose**
   ```bash
   docker-compose up --build
   ```

4. **Access the application**
   - Frontend: http://localhost:5000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Local Development without Docker

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   Optional browser support:
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **Run the services**
   ```bash
   # Terminal 1 - FastMCP research hub
   ./start_mcp.sh

   # Terminal 2 - Backend API
   uvicorn main:app --reload --port 8000

   # Terminal 3 - Frontend
   python app.py
   ```

### Local Development with Docker Compose

The default Docker setup runs four services:

- `postgres`
- `redis`
- `mcp` on `http://localhost:9000/mcp`
- `dev` for Flask + FastAPI on ports `3000` and `8000`

Start everything with:

```bash
docker-compose up --build
```

Health checks:

- App API: `http://localhost:8000/health`
- MCP hub: `http://localhost:9000/health`

## Research Architecture

The current migration target is a single research agent running on `gpt-5.4` with:

- FastMCP tools for search, fetch, browse, verification, and compaction
- Reusable project skills under `skills/`
- Explicit compacted research memory stored alongside conversation metadata
- Optional Playwright-backed browser access with HTTP fallback when Playwright is unavailable
- MCP-backed execution when `MCP_SERVER_URL` is set; local tool fallback otherwise

Relevant paths:

- `api/research/` - single-agent research flow and shared tool services
- `mcp_servers/research_hub/` - FastMCP tool server
- `skills/` - reusable workflow skills

## Docker Deployment

### Building the Docker Image

```bash
# Build the image
docker build -t deep-research:latest .

# Run the container
docker run -p 5000:5000 -p 8000:8000 \
  -e TAVILY_API_KEY=your_key \
  -e OPENAI_API_KEY=your_key \
  deep-research:latest
```

### Deploy to fly.io

1. **Install flyctl**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login and create app**
   ```bash
   fly auth login
   fly launch
   ```

3. **Set secrets**
   ```bash
   fly secrets set TAVILY_API_KEY=your_tavily_key
   fly secrets set OPENAI_API_KEY=your_openai_key
   ```

4. **Deploy**
   ```bash
   fly deploy
   ```

### Deploy to Render

1. **Create a new Web Service** on [Render Dashboard](https://dashboard.render.com/)

2. **Connect your GitHub repository**

3. **Configure the service**:
   - **Environment**: Docker
   - **Branch**: main
   - **Docker Command**: (leave default)
   - **Add Environment Variables**:
     - `TAVILY_API_KEY`
     - `OPENAI_API_KEY`

4. **Deploy** - Render will automatically build and deploy from your Dockerfile

## CI/CD Pipeline

The repository includes a GitHub Actions workflow that automatically builds and pushes Docker images to GitHub Container Registry (GHCR) when code is pushed to `main` or `develop` branches.

### Using the Docker Image from GHCR

```bash
# Pull the latest image
docker pull ghcr.io/<your-username>/deep_research:latest

# Run the image
docker run -p 5000:5000 -p 8000:8000 \
  -e TAVILY_API_KEY=your_key \
  -e OPENAI_API_KEY=your_key \
  ghcr.io/<your-username>/deep_research:latest
```

### Automatic Deployments

The workflow runs on:
- **Push to `main`**: Builds with `latest` tag (production)
- **Push to `develop`**: Builds with `develop` tag (staging)
- **Pull Requests**: Builds for testing (no push)

## Project Structure

```
deep_research/
├── api/                    # Backend modules
│   ├── orchestrator/      # Main orchestration agent
│   ├── web_search/        # Web search functionality
│   ├── code_executor/     # Code execution agent
│   ├── summarizer/        # Summary generation
│   └── verification/      # Verification agent
├── static/                # Frontend assets
│   ├── css/
│   ├── js/
│   └── img/
├── templates/             # HTML templates
├── main.py               # FastAPI backend
├── app.py                # Flask frontend
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Multi-container setup
└── requirements.txt      # Python dependencies
```

## PR Structure

- **main branch**: Production deployments
- **develop branch**: Integration branch for features
- **Feature branches**: Use `feat/<feature_name>` naming convention

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TAVILY_API_KEY` | Tavily web search API key | Yes |
| `OPENAI_API_KEY` | OpenAI API key for LLM | Yes |
| `FLASK_ENV` | Flask environment (development/production) | No |
| `API_URL` | Backend API URL for frontend | No |

## Contributing

1. Create a feature branch: `git checkout -b feat/your-feature`
2. Make your changes and commit
3. Push to your branch: `git push origin feat/your-feature`
4. Create a Pull Request to `develop` branch

## License

[Add your license here]
