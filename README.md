# Marketing AI: AI-Powered Marketing Automation Platform

A final year project (BSCS, Lahore Garrison University, session 2023-2027). Marketing AI helps small business owners keep a Facebook Page active. They type or speak what the business sells, and the app writes a marketing plan or post options, makes a picture with a headline, and publishes or schedules the post on their Facebook Page, **only after the owner agrees**.

Authors: Umer Irfan Khan (SP23-BSCS-158) and Ghulam Jelani (SP23-BSCS-173). Supervisor: Ms. Khola Farooq.

## Features

- **AI assistant:** a chat that returns a marketing plan, three post options (caption, description, hashtags, image prompt) or a short follow-up. It remembers the last 12 messages and a saved business profile.
- **Business memory:** a short profile of the business, updated in the background and editable on the History page.
- **Voice:** a microphone button in the chat and Autopilot. Speech is transcribed in English, Urdu or a mix, and replies can be read aloud by the browser.
- **AI pictures:** 1024x1024 images made from the idea, with a short headline drawn into the picture.
- **Create post:** guided, permission-gated steps: caption, picture, publish.
- **Autopilot:** one topic in, a finished post out. It writes the post, makes the picture, then publishes now or schedules at the suggested best time. Stop and Retry are supported.
- **7-day plan:** seven drafted posts reviewed by the user, then scheduled one per day.
- **Scheduled page:** waiting posts can be **edited** (text, publish time, picture) or removed; finished entries move to an Earlier list that can be cleared. A post that goes out in under 10 minutes can no longer be changed.
- **Review before posting:** Autopilot has an optional step to read and edit the text and replace the picture before anything goes out.
- **Email notifications:** the account address gets an email when a post is published, scheduled, goes live at its time, or is edited. Emails are sent by a background worker, so a slow mail server never slows a post down. On the History page the owner can switch emails off, send a test email, and see what happened to each one (sent, skipped or failed, with the reason). The server-wide switch is `POST_NOTIFICATIONS`.
- **Post performance:** the History page shows reactions, comments and shares of the latest posts, taken from Facebook and kept for 10 minutes.
- **Facebook in a small window:** connecting opens Facebook in a pop-up, so the page you are on never leaves and the browser's Back button keeps working. If pop-ups are blocked it falls back to a normal redirect.
- **Facebook Pages:** connect with Facebook Login (OAuth 2.0), save every Page you manage and choose which one to post to.
- **Secure sign-in:** email/password or Google through Firebase, always followed by a 6-digit code sent by email. Forgot-password uses the same kind of code.
- **Safe by design:** nothing is posted without confirmation, an Idempotency-Key stops double posts, Page tokens are encrypted.
- **Interface:** six dashboard pages (Overview, Autopilot, Create post, 7-day plan, Scheduled, History), light and dark theme.

## Tech Stack

| Layer          | Technology                                                                    |
| -------------- | ----------------------------------------------------------------------------- |
| Frontend       | React 19, Vite 8, Tailwind CSS 4, React Router 7, Axios                       |
| Backend        | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Pydantic                         |
| Database       | PostgreSQL (11 tables, created at start-up)                                   |
| Authentication | Firebase Authentication (browser) and Firebase Admin SDK (server), plus our own emailed 6-digit code |
| AI             | OpenAI: chat model (default `gpt-4.1-mini`), image model (default `gpt-image-1`), transcription (`gpt-4o-mini-transcribe`, then `whisper-1`). Each has an ordered fallback list. |
| Social         | Meta Graph API v23.0 (publishing and native scheduling)                       |
| Email          | Plain SMTP (Gmail, a transactional provider, or a local sandbox inbox)        |
| Security       | Fernet (stored Page tokens), HMAC (email codes, OAuth state)                  |
| Tests          | pytest, Vitest, Playwright                                                    |

## How It Works

```
React app (Vite, :5173)
   |  Firebase sign-in -> ID token;  every call sends  Authorization: Bearer <token>
   v
FastAPI backend (:8000)  -- idempotency + CORS middleware
   |  every protected route: verify token -> require confirmed email code -> load user
   |
   +--> PostgreSQL          users, conversations, messages, memory, Facebook Pages,
   |                        published and scheduled posts, email-code records
   +--> OpenAI              chat, images, speech to text
   +--> Meta Graph API      OAuth, publish, schedule, delete, status
   +--> SMTP server         sign-in and password-reset codes
```

Only the backend calls OpenAI, Meta and the mail server, so API keys, Page tokens and the mail password never reach the browser. Scheduled posts are handed to Facebook's own scheduler (15 minutes to 29 days ahead); the database keeps a record to list, remove and reconcile them.

## Project Structure

```
marketing-ai/
├── backend/
│   ├── app/
│   │   ├── core/        # config, Firebase, OpenAI client, Facebook API, OTP, password reset,
│   │   │                # mailer, token encryption, topic check, idempotency, error class
│   │   ├── db/          # engine, sessions, table creation
│   │   ├── models/      # the 11 SQLAlchemy models
│   │   ├── routers/     # auth, chat, facebook, images, autopilot, history, memory, schedule, voice
│   │   ├── schemas/     # request and response models
│   │   └── main.py      # app, middleware, router registration
│   ├── tests/           # pytest suite and the fake backend for browser tests
│   ├── tools/           # dev_mailbox.py: local sandbox inbox for sign-in emails
│   ├── .env.example
│   ├── requirements.txt
│   └── requirements-dev.txt
└── frontend/
    ├── src/
    │   ├── api/         # API calls
    │   ├── components/  # DashboardLayout, Autopilot, ChatBox, VoiceButton, ...
    │   ├── context/     # AuthContext (Firebase + email code state)
    │   ├── hooks/       # voice recorder, workspace, document title
    │   ├── pages/       # Intro, Login, Signup, ForgotPassword, VerifyOtp, and the six dashboard pages
    │   └── utils/       # topic and password rules, plan parser, speech text, tests
    ├── e2e/             # Playwright browser tests
    └── .env.example
```

## Getting Started

### Prerequisites

- Python 3.12 and Node.js 20+
- PostgreSQL
- A [Firebase](https://console.firebase.google.com/) project with Email/Password and Google sign-in enabled
- An [OpenAI](https://platform.openai.com/) API key with billing (pictures cost noticeably more than text)
- A [Meta for Developers](https://developers.facebook.com/) app with Facebook Login (only needed to publish)
- An SMTP account for the sign-in codes, or the local sandbox inbox for development

### 1. Database

```sql
CREATE DATABASE marketing_ai_db;
CREATE USER marketing_ai_user WITH PASSWORD 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON DATABASE marketing_ai_db TO marketing_ai_user;
```

Tables are created when the backend starts.

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

In the Firebase console go to **Project settings > Service accounts > Generate new private key** and save it as `backend/firebase-service-account.json`.

Copy `backend/.env.example` to `backend/.env` and fill in the values. The main settings:

| Setting | Purpose |
| --- | --- |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_MODELS` | chat model and optional fallback list |
| `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_MODELS`, `OPENAI_IMAGE_QUALITY` | image model, fallbacks, quality |
| `OPENAI_TRANSCRIBE_MODELS` | speech-to-text models, best first |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection (always set the password) |
| `FIREBASE_CREDENTIALS_PATH` | path to the service account file |
| `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_TOKEN_KEY` | Meta app and the key that encrypts Page tokens (if empty, one is created in `backend/.token_key`) |
| `FRONTEND_URL`, `BACKEND_URL` | allowed browser origin and OAuth callback base |
| `APP_ENV` | `development`, `test` or `production` (production refuses to start without email settings) |
| `SMTP_*` | mail server for the 6-digit codes and post notifications; the file shows three ready setups |
| `POST_NOTIFICATIONS`, `BACKGROUND_POLLER`, `POLL_SECONDS` | post emails on/off; the background check that announces posts going live, and how often it runs |

For development you can use the local sandbox inbox instead of real email. Start it in a second terminal, then open http://localhost:8025:

```bash
backend\venv\Scripts\python backend\tools\dev_mailbox.py
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

The API is at http://localhost:8000 and the interactive docs at http://localhost:8000/docs.

### 3. Frontend

```bash
cd frontend
npm install
```

Copy `frontend/.env.example` to `frontend/.env`, then set `VITE_API_BASE_URL` and the Firebase web app values (Firebase console > Project settings > Your apps). Start the dev server:

```bash
npm run dev
```

Open http://localhost:5173.

### 4. Connect Facebook (optional)

In your Meta app settings add this to **Valid OAuth Redirect URIs**:

```
http://localhost:8000/facebook/callback
```

The app asks for `pages_show_list`, `pages_read_engagement` and `pages_manage_posts`. While the Meta app is in development mode only people with a role on the app can connect; public use needs Meta app review.

## Running the Tests

Backend (pytest, in-memory SQLite, everything outside faked):

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Frontend unit tests, lint and build:

```bash
cd frontend
npm test
npm run lint
npm run build
```

Browser end-to-end tests (Playwright). They start a fake backend on port 8010 with Firebase, OpenAI, Facebook and email faked, so no real service is contacted:

```bash
pip install playwright
playwright install chromium
python frontend/e2e/test_e2e.py
```

The report records 181 backend tests, 75 frontend unit tests and 170 browser checks. After the later features (notifications, editing, performance, hardening) the suites hold 252 backend and 89 frontend unit tests, all passing; the 170 browser checks were not re-run. These automated runs never published to a real Facebook Page or used a real Firebase login.

## API Overview

All routes except `/`, `/auth/password/*` and the Facebook callback need `Authorization: Bearer <Firebase ID token>`. Errors from our own code use the shape `{"error": {"code", "message"}}`. Full details are at `/docs`.

| Area | Endpoints |
| --- | --- |
| Health | `GET /` |
| Auth | `POST /auth/sync`, `GET /auth/me`, `GET /auth/otp/status`, `POST /auth/otp/send`, `POST /auth/otp/verify`, `POST /auth/password/forgot`, `POST /auth/password/reset` |
| Chat | `POST /chat/plan`, `GET /chat/conversations`, `GET /chat/history/{id}`, `DELETE /chat/conversations/{id}` |
| Memory | `GET`, `PUT`, `DELETE /memory` |
| Voice | `POST /voice/transcribe` |
| Pictures | `POST /images/generate` |
| Autopilot | `POST /autopilot/post` |
| Facebook | `GET /facebook/connect-url`, `GET /facebook/callback`, `GET /facebook/status`, `GET /facebook/pages`, `POST /facebook/select-page`, `POST /facebook/publish`, `POST /facebook/publish-photo`, `POST /facebook/disconnect` |
| Schedule | `POST /schedule/draft`, `POST /schedule/post`, `GET /schedule`, `PUT /schedule/{id}`, `DELETE /schedule/{id}`, `POST /schedule/cancel-all`, `DELETE /schedule/earlier/{id}`, `POST /schedule/clear-earlier`, `GET /schedule/best-time` |
| History | `GET /history/posts`, `GET /history/insights` |
| Notifications | `GET /notifications`, `PUT /notifications/settings`, `POST /notifications/test` |
| Health | `GET /health` (is the process up), `GET /ready` (can it reach the database) |

`/facebook/publish`, `/facebook/publish-photo` and `/schedule/post` accept an `Idempotency-Key` header: a repeat while the first call runs gets 409, and a repeat after success returns the stored answer without posting again.

## Running it for real users

### With Docker

```bash
cp backend/.env.example backend/.env      # fill it in; put firebase-service-account.json in backend/
# create a file named .env next to docker-compose.yml with:
#   DB_PASSWORD=<a strong password>
#   FACEBOOK_TOKEN_KEY=<a Fernet key>     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   VITE_API_BASE_URL=https://api.yourdomain.com and the VITE_FIREBASE_* values
docker compose up --build                 # site on :8080, API on :8000
```

The compose file starts PostgreSQL, the backend (one process, as a normal user, with a health check) and the website behind nginx. Those Docker files have not been built or run on the machine that wrote them, so run `docker compose build` once before relying on them.

### Checklist

- `APP_ENV=production`. The backend then refuses to start with the default database password or without email settings.
- Serve both the site and the API over HTTPS. In production the API sends the `Strict-Transport-Security` header.
- Set `FRONTEND_URL` to the real site address (it is the only browser origin the API accepts besides localhost) and add the real callback address to your Meta app's **Valid OAuth Redirect URIs**.
- Send email from a real address on your own domain (SPF and DKIM set up), or the code and notification emails may land in spam.
- Run **one** backend process. Duplicate-post protection and the rate limits keep their counts in memory.
- Keep `.env`, `.token_key` and the Firebase file out of git, and back up the database.
- Meta app review is still needed before people outside your app's team can connect their Pages.

What the API does for you in production: every response has an `X-Request-ID` (also in the log line and in error answers), safe headers (`nosniff`, no framing, no caching of private answers), clean `{"error": {"code", "message"}}` answers even for unexpected failures, and per-user limits on the calls that cost money (chat, pictures, voice, Autopilot, week plans). Backend requirements are pinned to the versions the tests ran against, and `.github/workflows/ci.yml` runs the backend tests, lint, frontend tests and the build on every push.

## Limitations

- Facebook Pages only (no Instagram or LinkedIn); no analytics dashboard.
- Scheduled posts can be removed but not edited.
- Publishing and scheduling were tested against a simulated Facebook, not a real Page. The Meta app is in development mode.
- Best-time guidance uses your own post engagement once the selected Page has at least 10 posts; before that it is an AI general guide, clearly labelled as not measured.
- Idempotency keys are held in memory, which is enough for a single backend process.
- No load test, no formal user study, and transcription accuracy was not measured.

## Security

Never commit `backend/.env`, `backend/.token_key`, `backend/firebase-service-account.json` or `frontend/.env`. If a key is ever pushed by mistake, revoke it and create a new one right away. Passwords are held only by Firebase; Page tokens are encrypted with Fernet; sign-in codes are stored only as HMAC hashes.
