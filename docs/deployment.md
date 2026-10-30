# Deploying MetaboSquad

This document describes how to deploy MetaboSquad on a Linux server and serve it publicly through nginx.
The domain `metabosquad.example.org` is an example; replace it with your own domain.

## Contents

- [Installing dependencies (three Linux pitfalls)](#installing-dependencies-three-linux-pitfalls)
- [Environment variables](#environment-variables)
- [Nginx](#nginx)
- [Cloudflare](#cloudflare)
- [Demo data](#demo-data)
- [Pre-launch checklist](#pre-launch-checklist)
- [Known limitations](#known-limitations)

---

## Installing dependencies (three Linux pitfalls)

`requirements.txt` was generated on Windows, so running `pip install -r requirements.txt`
directly on Linux used to fail. Two issues have been fixed:

- `psycopg2` → `psycopg2-binary` (the original tries to compile from source, which needs `pg_config` and a build toolchain)
- `pywin32==312` now has the environment marker `; sys_platform == "win32"` (it is a Windows-only package
  that cannot be installed on Linux; the marker lets both platforms use the same file)

**A third pitfall remains and you must handle it manually: `torch` pulls a ~3GB CUDA wheel.**

`torch==2.13.0` is a dependency of `easyocr` (the OCR in the `plot_review` path needs it), but
`backend/src/graph_agent/use_tool/plot_tool.py` explicitly uses `easyocr.Reader(["en"], gpu=False)`,
which means **it does not use the GPU at all**. The default install downloads the full CUDA build (in our tests it hung for more than ten minutes).

The CPU build is sufficient (under PEP 440, `==2.13.0` matches `2.13.0+cpu`, so you do not need to change requirements.txt):

```bash
cd backend
python -m venv venv
source venv/bin/activate

# Install the CPU build of torch first, so it is not pulled in as the CUDA build later (~250MB vs ~3GB)
pip install torch==2.13.0+cpu --index-url https://download.pytorch.org/whl/cpu

pip install -r ../requirements.txt
pip install -r requirements-dev.txt      # for testing (pytest)

# requirements.txt pulls torchvision from PyPI, which does not match the CPU torch.
# Replace it with the CPU build of the same version.
pip install torchvision==0.28.0+cpu --index-url https://download.pytorch.org/whl/cpu
```

If you skip the last step, `import torchvision` fails with
`RuntimeError: operator torchvision::nms does not exist`, and 4 test files fail during collection.

After installation, verify:

```bash
venv/bin/python -m pytest tests/ -q      # all tests should pass
```

> **Always run the tests with `venv/bin/python -m pytest`**, not a bare `pytest`.
> The system-wide pytest does not have `sqlmodel` and fails immediately with `ModuleNotFoundError`.

You still need to build the MetaboAnalystR Docker image as described in the README (`meta_image:v3`; **do not change the name**,
it is hard-coded in the source).

The memory limit of the R container is `2g` (`use_tool/code.py`). The original `512m` made the
analysis of the demo data fail with exit 137 (OOM), and the failure was hard to see: the R statistics
actually finished, and the process died in the plotting module afterwards. The only visible message was "Analysis results CSV not found.".
In our measurements the threshold lies between 512m and 768m; `tests/test_r_container_limits.py` guards the lower bound.

`mummichog` is an external CLI used by the pathway feature (`pip` installs it into `venv/bin/`). Note that
`venv/bin/python -m uvicorn` does **not** activate the venv, so `venv/bin` is not on PATH.
At startup, `main.py` adds the interpreter's directory to PATH itself (guarded by `tests/test_venv_bin_on_path.py`),
so you do not need to activate the venv manually. Without this step, the report says that the `mummichog`
command was not found on the system, which looks like it is not installed.

---

## Environment variables

### `backend/.env`

```
OPENAI_API_KEY=sk-...
PG_URL=postgresql://user:pass@host:5432/metabosquad
TEST_PG_URL=postgresql://user:pass@host:5432/metabosquad_test
EMAIL=your_email@example.com
# NCBI_KEY must either have a value or be absent entirely; it must not be left empty (see below)
NCBI_KEY=your_key
CORS_ORIGINS=https://metabosquad.example.org
```

`CORS_ORIGINS` is comma-separated. **If it is unset or empty, it falls back to a localhost list and
prints a warning line in the startup log.** If the browser blocks every frontend request after deployment, check this line first.

**Do not set** `SKIP_AGENT_INIT`. It is a bypass for tests; if set, the agent is `None` and every conversation fails.

**`NCBI_KEY` must not be left empty.** `os.getenv` reads an empty string as `''` (not `None`),
`search.py` passes it unchanged to Entrez, Biopython then puts `api_key=` into the URL, and NCBI returns
**HTTP 400**. Literature search then always returns 0 papers, and the user only sees "zero papers found" with no error message.
Either fill in a real key ([free registration](https://www.ncbi.nlm.nih.gov/account/settings/), which raises the rate limit from
3 to 10 req/s), or comment out the whole line.

### `frontend/.env.production`

```
NEXT_PUBLIC_API_BASE=https://metabosquad.example.org
```

`NEXT_PUBLIC_*` values are written into the bundle at `npm run build` time; **they are not read at runtime**. If you change this value,
you must rebuild; a restart alone has no effect. (See `frontend/.env.example` for the template.)

---

## Nginx

**`proxy_buffering off` is required.** Otherwise nginx buffers the whole SSE stream until the request ends and sends it all at once.
The user sees a frozen screen for several minutes and then everything appears at once. The execution trace then loses its meaning,
and with it the purpose of showing the user that the system has not hung.

```nginx
server {
    listen 443 ssl http2;
    server_name metabosquad.example.org;

    ssl_certificate     /etc/nginx/ssl/example.org/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/example.org/privkey.pem;

    client_max_body_size 64m;   # peak table CSVs can be large

    # Frontend
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API (including SSE)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # ── Required SSE settings ──
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection "";
        chunked_transfer_encoding off;
        # literature_search is the slowest path: abstract_extract_node has no upper
        # limit on the number of papers sent to abstract extraction, and makes one LLM
        # call per paper (10 concurrent). About 74 papers took 10 minutes in our tests,
        # so 600s would cut the stream midway. 1800s is a margin for the worst case.
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;
    }

    # Generated files (figures, reports, ZIPs)
    location /uploads/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

Raising `proxy_read_timeout` to 1800s is also required: an `analysis` run through statistics → PubChem → pathway
often exceeds the default 60 seconds, and `literature_search` takes even longer. Abstract extraction makes one LLM call per paper
(`literature_scoping_only_pubmed.py:160`, `chunk_size=1`, 10 concurrent) **and has no upper limit on the number of papers**;
about 74 papers took 10 minutes in our tests. A timeout cuts the stream midway, and the user only sees the screen stop updating.

The wait time for literature search depends on the scope of the question. When the question is narrowed to, for example, "mechanism + cell type + last five years",
PubMed hits can drop from 2767 papers to about 171.

---

## Cloudflare

Use Full mode. **After deployment, you must test that SSE events arrive one at a time**:

```bash
curl -N -H "Content-Type: application/json" \
  -d '{"message":"Look up citric acid"}' \
  https://metabosquad.example.org/api/chat/<thread_id>
```

`-N` turns off curl's own buffering. Events should appear **one at a time, in real time**. If they all arrive at once at the end,
some layer is still buffering. Check in this order:

1. Whether nginx has `proxy_buffering off`
2. Cloudflare: if needed, add a Configuration Rule for `/api/chat/*` that turns off caching

Cloudflare closes a proxied connection after about 100 s with no bytes (HTTP 524). One literature
step (abstract screening) can stay silent longer than that on a large query. While it waits, the
backend sends an SSE comment line (`: keepalive`) every `SSE_HEARTBEAT_SECONDS` (30 s,
`api/routers/chat.py`). In the `curl -N` output above, these lines appear between events; they are expected.

---

## Demo data

The repo includes two demo files that you can use directly to try the analysis and figure-review features:

| File | Used by | Source |
| :--- | :--- | :--- |
| `backend/uploads/csv/lcms_table.csv` | `analysis` | Example data from the Data Formats page of the MetaboAnalyst 6.0 website: a peak intensity table of mouse spinal cord samples (two groups). <https://www.metaboanalyst.ca/docs/Format.xhtml> |
| `backend/uploads/image/benchmark_semantic_pca_01.png` | `plot_review` | A demo figure made for this project: plotted from LLM-generated synthetic data; it does not represent any real experimental result. |

`tests/test_gitignore_covers_agent_output.py` checks that these two files stay under version control,
and that all other files under `uploads/` (agent output and user-uploaded data) are excluded by `.gitignore`.

---

## Pre-launch checklist

- [ ] `pip install` completed in the order above (CPU torch first), and `venv/bin/python -m pytest tests/ -q` passes
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build` all pass
- [ ] `CORS_ORIGINS` includes the production domain (otherwise the browser blocks every frontend request; the startup log shows a fallback warning)
- [ ] `NEXT_PUBLIC_API_BASE` points to the production domain, **and the frontend has been rebuilt**
- [ ] `SKIP_AGENT_INIT` is **not** set; `NCBI_KEY` has a value or the line is absent (**do not leave it empty**)
- [ ] `OPENAI_API_KEY` is a real key (a dummy key lets the service start, but every conversation fails)
- [ ] SSE tested with `curl -N`: events arrive one at a time
- [ ] Upload a 20MB CSV to confirm that `client_max_body_size` does not block it

---

## Known limitations

1. **No user accounts or access control.**
   Everyone who connects to the service shares the same workspace: the sidebar lists all conversations, anyone who knows a `thread_id`
   can read that conversation, and `/uploads` is a public static mount. Path-traversal protection in the API layer is complete
   (`commonpath`, which also blocks symlink escapes), but the uploads tree itself is shared.
   If you expose the service publicly, put an authentication layer in front of it (for example nginx basic auth or SSO).

2. **The content of full reports is still in Chinese.**
   The interface itself is bilingual, but the **report content** of `plot_review`/`id_mapping` is generated by the backend agents
   and is not controlled by the frontend i18n.

3. **The en strings use a fallback mechanism.**
   The type of `en` is `Partial<Record<keyof typeof zh, string>>`; if a key is missing, it falls back with `?? zh`.
   Tests guard the alignment of zh/en keys
   (`describe("zh / en key parity in the messages tables")` in
   `frontend/src/i18n/__tests__/i18n.test.tsx`), so a missing translation turns a test red instead of silently showing Chinese.

4. **Multi-file upload is not supported** (only one file at a time).
