# face_chat — AI city

An AI chat API with agents. You give an agent a task, it works in the background with
its tools, and asks you before doing anything risky.

```
 you ──▶ POST /tasks ──▶ agent (ops) ──▶ model (Ollama cloud)
                            │  ▲
                   tool call│  │result
                            ▼  │
                          tools: check_website, current_time,
                                 run_command (waits for your approval)
```

## Run

```bash
pip install -r requirements.txt
cp .env.example .env              # set OLLAMA_API_KEY
alembic upgrade head              # only for an existing database; a new one is created on start
python main.py create-user you@example.com   # prints your API key (valid 365 days)
python main.py
```

Open http://localhost:8000/docs, click **Authorize** and paste the key. Every request
sends it as `X-API-Key: <key>`. More keys: `POST /apikeys/generate`.

## Agents

```bash
KEY=...    # from create-user

# Give the ops agent a job
curl -X POST localhost:8000/tasks -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"prompt": "Is https://conf.mtutoshkent.uz up? How fast?"}'

curl localhost:8000/tasks/<id> -H "X-API-Key: $KEY"           # status, result, every step
curl -X POST localhost:8000/tasks/<id>/approve -H "X-API-Key: $KEY"   # or /reject
```

Task status: `queued` → `running` → `done` / `failed`, or `waiting_approval` when the
agent wants a tool that needs your OK. `waiting_for` shows which tool and arguments.

| Endpoint | |
|---|---|
| `GET /agents` | Agents and their tools |
| `POST /tasks` | `{"prompt": "...", "agent": "ops", "model": null}` |
| `GET /tasks`, `GET /tasks/{id}` | List, or one task with all steps |
| `POST /tasks/{id}/approve`, `/reject` | Answer a waiting tool call |

- **Add a tool:** an async function returning a string, plus a `Tool(...)` in
  `src/agents/tools.py`. Use `needs_approval=True` for anything that changes something.
- **Add an agent:** an `Agent(...)` in `src/agents/registry.py` with its prompt and tools.
- **Shell access:** `ENABLE_SHELL_TOOL=true` gives the ops agent `run_command`. Each
  command still waits for approval.

Tasks run inside the API process. If the server restarts, running tasks are marked failed.

## Chat

The plain chat endpoints are unchanged: `/chat/new`, `/chat/list`, `/chat/{chat_id}`,
`/chat/ai/models`.
