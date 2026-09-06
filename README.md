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

## How to run the app

Do these steps in order the first time. After that, jump to [Start it again](#start-it-again).

### 0. What you need installed

- Python 3.10 or newer  
- Node.js 18 or newer  
- [FFmpeg](https://ffmpeg.org/) on your PATH (`ffmpeg -version` should work)

### 1. Open the project

```powershell
git clone https://github.com/2022CS11103/podcast-to-campaign.git
cd podcast-to-campaign
```

If you already have the folder, just `cd` into it (for example `C:\Users\hp\Downloads\creator-os`).

### 2. Create a virtualenv and install Python packages

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Add a `.env` file

In the **repo root** (same folder as `api/`), create `.env`. Do not commit this file.

```
GEMINI_API_KEY=your_key
FRONTEND_URL=http://127.0.0.1:8000/app
```

You can rotate keys with `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, and so on.

For optional Stripe paywall env vars, see **Stripe subscriptions** below.

Optional - YouTube publish:

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/youtube/callback
```

Optional - Instagram / LinkedIn / X connect, plus `OAUTH_TOKEN_ENCRYPTION_KEY`.

Studio login works with email/password with no extra setup. Google sign-in needs `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in the frontend env, then a frontend rebuild.

### 4. Build the studio UI

FastAPI serves the built files in `frontend/dist`. You must build at least once:

```powershell
cd frontend
npm install
npm run build
cd ..
```

### 5. Start the server

From the **repo root**, with the venv still active:

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

macOS/Linux:

```bash
export PYTHONIOENCODING=utf-8
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Leave this terminal running. Do **not** use `--reload` for this pipeline - restart the process after Python changes.

### 6. Open the app

In a browser:

**http://127.0.0.1:8000/app/**

1. Create an account (or sign in).  
2. You land on **Accounts** - connect channels or skip.  
3. Go to **Content**, paste a YouTube/podcast URL or upload a video.  
4. Set how many posts per platform, then generate.  
5. Stay on the processing page until the campaign is ready, then review Library and Calendar.

Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) should return `{"status":"ok"}`.

### Start it again

After the first setup, each session is only:

```powershell
cd podcast-to-campaign
.\.venv\Scripts\activate
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Then open **http://127.0.0.1:8000/app/** again.

### Stripe subscriptions (optional paywall)

CreatorOS gates generation by **campaign length** — the same 14 / 30 / 45 / 60-day options as the campaign picker.

1. Create four recurring Prices in the [Stripe Dashboard](https://dashboard.stripe.com/) (or one yearly that unlocks all).
2. Add to the project `.env`:

```env
BILLING_ENABLED=true
BILLING_ENFORCE=true
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_CAMPAIGN_14=price_...
STRIPE_PRICE_CAMPAIGN_30=price_...
STRIPE_PRICE_CAMPAIGN_45=price_...
STRIPE_PRICE_CAMPAIGN_60=price_...
STRIPE_PRICE_CAMPAIGN_14_LABEL=$19/mo
STRIPE_PRICE_CAMPAIGN_30_LABEL=$29/mo
STRIPE_PRICE_CAMPAIGN_45_LABEL=$39/mo
STRIPE_PRICE_CAMPAIGN_60_LABEL=$49/mo
# Optional annual unlock (covers all durations):
STRIPE_PRICE_PRO_YEARLY=price_...
STRIPE_PRICE_PRO_YEARLY_LABEL=$290/yr
# Legacy alias: STRIPE_PRICE_PRO_MONTHLY maps to the 30-day pack
FRONTEND_URL=http://127.0.0.1:8000
BILLING_BYPASS_EMAILS=you@example.com
```

3. Install the SDK: `pip install stripe`
4. Point a Stripe webhook to `POST /webhooks/stripe` for:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`
5. Restart Uvicorn. Users pick a pack on **Billing**; Strategy highlights the pack that matches their campaign duration. Generating a longer calendar than the pack allows returns **402**.

Leave `BILLING_ENFORCE` unset while testing (recommended). Generation stays open; packs can still show as a preview if `BILLING_ENABLED=true`. Checkout and the Strategy paywall only run when **both** `BILLING_ENABLED` and `BILLING_ENFORCE` are on with a real `sk_test_…` / `sk_live_…` key.

### If you change the code

| What you changed | What to do |
| --- | --- |
| `frontend/src/...` | `cd frontend` → `npm run build` → hard-refresh `/app/` |
| Python (`api/`, `scripts/`, `utils/`) | Stop Uvicorn (Ctrl+C) and start it again |

Optional local UI hot-reload (API must already be on port 8000):

```powershell
cd frontend
npm run dev
```

Then open the Vite URL (usually `http://127.0.0.1:5173/app/`). For a single URL that matches production, prefer `npm run build` + Uvicorn.

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
