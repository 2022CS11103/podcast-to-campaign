# CreatorOS

**One video. A month of content.**

creatorOS is an AI content operating system. Upload one podcast, interview, or long-form video and it plans, edits, and schedules a multi-platform campaign - Shorts, Reels, LinkedIn posts, and X - with a 30-day calendar you control.

Create once. Repurpose everywhere.

## What it does

1. **Ingest** a YouTube / podcast URL or a local video upload  
2. **Find** the moments worth posting (hook, payoff, skip the ramble)  
3. **Edit** vertical cuts: stitch, speaker-follow 9:16, captions, jump-cuts  
4. **Write** platform-specific copy (not copy-paste)  
5. **Plan** a month of posts you can pause, skip, or stop per platform  

The calendar is a **plan**. Nothing publishes until you approve it. YouTube upload exists; Instagram, LinkedIn, and X can be connected for later publishing.

## Stack

| Layer | Tech |
| --- | --- |
| App | React + Vite (`frontend/`), served at `/app/` |
| API | FastAPI (`api/main.py`) |
| Models | Gemini for strategy / copy / edit direction |
| Media | FFmpeg, OpenCV, Whisper / faster-whisper |
| Auth | Local accounts by default; optional Supabase + Google |

## Quick start

**Needs:** Python 3.10+, Node.js, [FFmpeg](https://ffmpeg.org/) on your PATH.

```powershell
cd creator-os
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..

$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Open [http://127.0.0.1:8000/app/](http://127.0.0.1:8000/app/).

After frontend changes, run `npm run build` in `frontend/` and hard-refresh `/app/`. Restart Uvicorn after Python changes (do not rely on `--reload` for this pipeline).

## Environment

Create a `.env` in the repo root (never commit it):

```
GEMINI_API_KEY=your_key
# or rotate several: GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...

FRONTEND_URL=http://127.0.0.1:8000/app

# Optional — YouTube publish
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/youtube/callback

# Optional — Instagram / LinkedIn / X connect
# plus OAUTH_TOKEN_ENCRYPTION_KEY
```

Studio login works locally with email/password. For Google sign-in and cloud accounts, set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in the frontend env and rebuild.

## Using the studio

1. Sign in - you land on **Accounts** with a 3-step guide  
2. Connect channels (optional) or skip  
3. **Content** - paste a URL or upload a file  
4. Shape counts per platform, then generate  
5. Watch **creatorOS is thinking**; stop one platform or the whole run if you want fewer posts  
6. Review the library and **Calendar** - pause a channel or skip a day anytime  

## Repo map

```
api/                 FastAPI, jobs, schedule hold/resume/skip
frontend/            React studio (source + dist)
scripts/ai/          Director, ranker, narrative packing
scripts/video/       Executor, reframe, B-roll, quality
scripts/pipeline/    Download, transcribe, highlight scan
config/              Editing rules and platform specs
utils/               Calendar, Gemini client, OAuth
output/              Generated campaigns (gitignored)
```

## Honest limits

- Scan is audio-first by default (`VIDEO_ANALYSIS_ENABLED = False`) for speed  
- Calendar dates are scheduled **plans**, not a daily auto-poster  
- Stock B-roll, music beds, and natural-language “make the intro faster” chat are not in this build  

## License

Private project. Ask before reusing.
