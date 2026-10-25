# MetaboSquad
### Metabolomics Multi-Agent Intelligent Assistant
This project is an AI Assistant for Literature Searching and Data Analysis in Metabolomics

Metabolomics research involves complex steps that require domain knowledge and specialized skills. These steps can be very challenging, especially for researchers without programming skills. Our system uses specialized AI agents, coordinated by a supervisor agent, to simplify the analysis workflow.

## Project structure

```
project/
├── frontend/          # Next.js
├── backend/           # Python (FastAPI)
├── metabo_docker      # Docker environment build files
└── requirements.txt   # Dependencies
```
---

## Quick start

### 1. Edit the environment variable template

Edit `backend/.env.sample`, fill in the required settings (database connection, API keys, etc.), and rename the file to `.env`.

### 2. Set up the environment
```python
pip install -r requirements.txt
```

### 3. In metabo_docker, build the MetaboAnalystR 4.0 runtime environment # takes about 2 minutes

```bash
docker build -t meta_image:v3 . --no-cache
```
##### Do not change the image name (meta_image:v3)

### 4. Generate the pathway database

Pathway enrichment needs a KEGG gene-set file, which is not distributed with this repository.
Generate it locally (a few minutes):

```bash
cd ./backend
venv/bin/python -m src.graph_agent.use_tool.download_path_db
```

See `backend/src/graph_agent/database/README.md` for the KEGG version used in the manuscript.

### 5. Test the agent
After the build finishes, you can test the agent with `test_agent.py`
```bash
cd ./backend
python -m test_agent
```

### 6. Build and start all services
##### Start the backend
```python
cd ./backend
python -m uvicorn main:app
```
##### Install the project dependencies and start the frontend
```python
cd ./frontend
npm install
npm run dev
```
Press ctrl+c to stop the frontend and backend

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs


---
## Development

### Tests

```bash
cd backend && venv/bin/python -m pytest tests/ -q     # backend tests
cd frontend && npm test && npm run typecheck          # frontend tests and type check
```

Always run the backend tests with `venv/bin/python -m pytest`: the global pytest does not have `sqlmodel`.
`npm test` does not type-check, so run `npm run typecheck` separately. A type error makes
`npm run build` fail even when all tests pass.

### Related documents

- Deployment (including the required nginx settings for SSE and the three Linux installation pitfalls): `docs/deployment.md`
- Figure-review benchmark: `backend/benchmarks/README.md`


---
## Changing the model

### 1. gemma4:26b

Edit the # ===== Ollama ===== section and fill in the required settings
- `backend/src/graph_agent/supervisor.py` (change the passed-in literature_scoping to literature_gemma)
- `backend/src/graph_agent/tools.py`
- `backend/src/graph_agent/graph/plot_graph.py`

---
## License

MetaboSquad is released under the [MIT License](LICENSE).
Pathway data from KEGG and SMPDB are not covered by this license; they are subject to their providers' terms of use.
