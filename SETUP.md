# Setup — Zip to Running Demo

## 1. Get the code onto your machine

1. Download `person_a_backend.zip` and extract it, e.g. `~/hackathon/person_a_backend`.
2. Check prerequisites:
   ```bash
   python3 --version   # need 3.10+
   code --version       # VS Code
   ```
3. Open it:
   ```bash
   cd ~/hackathon/person_a_backend
   code .
   ```

## 2. Python environment

Open a VS Code terminal in the project folder.

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

Select the `./venv` interpreter when VS Code prompts you. Checkpoint (no keys, no internet needed):
```bash
pytest tests/
```
Expect `51 passed`. If this fails, fix it before touching API keys.

## 3. API keys, in priority order

```bash
cp .env.example .env
```
Fill in `.env` as you go. **Only step 1 below is required** — everything else upgrades an already-working keyless pipeline.

1. **Gemini (required — Module 3)**: https://aistudio.google.com/apikey → Create API key → paste as `GEMINI_API_KEY`. Free, no card.
2. **AQICN (recommended, 2 min)**: https://aqicn.org/data-platform/token/ → email → paste as `AQICN_TOKEN`.
3. **OpenAQ (optional upgrade)**: https://explore.openaq.org/register → `OPENAQ_API_KEY`.
4. **data.gov.in (optional fallback tier)**: https://api.data.gov.in → `DATAGOVIN_API_KEY`.
5. **NASA FIRMS (optional upgrade)**: https://firms.modaps.eosdis.nasa.gov/api/map_key/ → `FIRMS_MAP_KEY`.
6. **Reddit PRAW (optional upgrade)**: https://www.reddit.com/prefs/apps → create "script" app → `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`.
7. **Kaggle (optional, last-resort fallback)**: https://www.kaggle.com/settings → API → Create New Token → `KAGGLE_USERNAME` / `KAGGLE_KEY` from the downloaded `kaggle.json`. Also open the dataset page once in-browser and click Download to accept its terms.

## 4. Run it

**Batch script** (logs everything to console, no server):
```bash
python run_demo.py
```
Needs real internet (unlike the pytest checkpoint). Watch for `WARNING` lines — they mean a source fell back to cache, not a crash. Successful pulls cache CSVs into `cache/` and charts into `cache/*.png` — **commit `cache/` to git** as your offline demo-day fallback.

**HTTP API** (what Person B's frontend actually talks to):
```bash
uvicorn api:app --reload
```
Same live-internet requirement as `run_demo.py` — it runs the identical pipeline for `PRIMARY_CITY`/`COMPARISON_CITIES` once at startup before it starts accepting requests, so first boot is slow (real network calls to every source in `data_pipelines/`), everything after is instant. Once "Application startup complete" appears, open http://127.0.0.1:8000/docs — that page is the full API reference, see the README's "For Person B" section for the endpoint list.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` | venv not activated / VS Code interpreter not switched — redo `pip install -r requirements.txt` |
| `pytest` fails pre-keys | Check `python --version` (need 3.10+), redo install |
| `GEMINI_API_KEY is not set` | Confirm `.env` is in the project root, next to `config.py` |
| `429` from Gemini | Free-tier rate limit — wait ~1 min, don't loop-call in testing |
| `requests.HTTPError` from a pipeline | That source is down/limited — caching auto-falls back; check the log |
| `All AQI sources exhausted` | No internet AND no cache yet — run once with internet first so `cache/` populates |
