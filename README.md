# AI Marketing Automation Platform

An AI-powered marketing assistant for small businesses. Describe your business, and the app generates a practical marketing plan, social media captions, and content ideas. You can then publish posts and photos straight to your Facebook Page, without leaving the app.

## Features

- **AI marketing plans:** Chat with an AI marketing strategist (Mistral-7B Instruct via Hugging Face) that tailors advice to your business name and industry.
- **Saved chat history:** Every conversation is stored in PostgreSQL, so you can come back and continue where you left off.
- **User accounts:** Sign up and log in with email/password or Google, powered by Firebase Authentication.
- **Facebook Page integration:** Connect a Facebook Page through Facebook Login, then publish text posts or photos with captions directly from the dashboard.
- **Protected routes:** Only signed-in users can reach the dashboard. The backend verifies every request with a Firebase ID token.

## Tech Stack

| Layer          | Technology                                                    |
| -------------- | ------------------------------------------------------------- |
| Frontend       | React 19, Vite, Tailwind CSS 4, React Router, Axios           |
| Backend        | FastAPI, Uvicorn, SQLAlchemy                                  |
| Database       | PostgreSQL                                                    |
| Authentication | Firebase Authentication (client) + Firebase Admin SDK (server) |
| AI             | Mistral-7B Instruct via the Hugging Face Inference Router     |
| Social         | Facebook Graph API (v23.0)                                    |

## How It Works

```
React frontend ──(Firebase ID token)──▶ FastAPI backend ──▶ PostgreSQL (users, conversations, messages)
      │                                      │
      └── Firebase Auth (login/signup)       ├──▶ Hugging Face (Mistral) for marketing replies
                                             └──▶ Facebook Graph API for publishing posts
```

1. The user signs in on the frontend with Firebase.
2. The frontend sends the user's Firebase ID token with each API request.
3. The backend verifies the token, creates the user in PostgreSQL if needed, and handles the request.
4. Chat messages go to the AI model, and both the question and the reply are saved to the conversation.
5. To publish, the user connects a Facebook Page once, then posts text or photos from the dashboard.

## Project Structure

```
marketing-ai-project/
├── backend/
│   ├── app/
│   │   ├── core/          # Settings, Firebase Admin, AI model clients
│   │   ├── db/            # Database connection and table creation
│   │   ├── models/        # SQLAlchemy models: User, Conversation, Message
│   │   ├── routers/       # API routes: auth, chat, facebook
│   │   ├── schemas/       # Request/response models
│   │   └── main.py        # FastAPI app entry point
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── api/           # Axios client and Facebook API calls
    │   ├── components/    # Navbar, ChatBox
    │   ├── context/       # AuthContext (Firebase auth state)
    │   ├── firebase/      # Firebase client config
    │   └── pages/         # Login, Signup, Home (dashboard)
    └── package.json
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 20+
- PostgreSQL
- A [Firebase](https://console.firebase.google.com/) project with Email/Password and Google sign-in enabled
- A [Hugging Face](https://huggingface.co/settings/tokens) access token
- A [Meta for Developers](https://developers.facebook.com/) app with Facebook Login (only needed for publishing)

### 1. Clone the repository

```bash
git clone https://github.com/XUmer007/ai-marketing-automation-platform.git
cd ai-marketing-automation-platform
```

### 2. Set up the database

Create a PostgreSQL database and user. The tables are created automatically when the backend starts.

```sql
CREATE DATABASE marketing_ai_db;
CREATE USER marketing_ai_user WITH PASSWORD 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON DATABASE marketing_ai_db TO marketing_ai_user;
```

### 3. Set up the backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

In the Firebase Console, go to **Project settings → Service accounts → Generate new private key**. Save the file as `backend/firebase-service-account.json`.

Then create a `backend/.env` file:

```env
APP_NAME=Marketing AI Backend
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000

# Firebase Admin
FIREBASE_CREDENTIALS_PATH=firebase-service-account.json

# Hugging Face
HF_TEXT_TOKEN=your_hugging_face_token
HF_TEXT_MODEL=mistralai/Mistral-7B-Instruct-v0.2:featherless-ai
HF_IMAGE_TOKEN=your_hugging_face_token
HF_IMAGE_MODEL=stabilityai/stable-diffusion-xl-base-1.0

# PostgreSQL
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=marketing_ai_db
DB_USER=marketing_ai_user
DB_PASSWORD=your_database_password

# Facebook
FACEBOOK_APP_ID=your_facebook_app_id
FACEBOOK_APP_SECRET=your_facebook_app_secret
```

Start the server:

```bash
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000. Interactive API docs are at http://localhost:8000/docs.

### 4. Set up the frontend

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Put your own Firebase web app config in `frontend/src/firebase/firebase.js`, then start the dev server:

```bash
npm run dev
```

Open http://localhost:5173 in your browser.

### 5. Connect Facebook (optional)

In your Meta app settings, add this to **Valid OAuth Redirect URIs**:

```
http://localhost:8000/facebook/callback
```

The app requests these permissions: `pages_show_list`, `pages_read_engagement` and `pages_manage_posts`.

## API Endpoints

| Method | Endpoint                      | Description                                         |
| ------ | ----------------------------- | --------------------------------------------------- |
| GET    | `/`                           | Health check                                        |
| GET    | `/auth/me`                    | Get the signed-in user's profile                    |
| POST   | `/auth/sync`                  | Create or update the user in the database           |
| POST   | `/chat/plan`                  | Send a message and get an AI marketing reply        |
| GET    | `/chat/conversations`         | List the user's conversations                       |
| GET    | `/chat/history/{id}`          | Get all messages in a conversation                  |
| GET    | `/facebook/connect-url`       | Get the Facebook Login URL                          |
| GET    | `/facebook/callback`          | Facebook OAuth callback                             |
| GET    | `/facebook/status`            | Check whether a Facebook Page is connected          |
| POST   | `/facebook/publish`           | Publish a text post to the connected Page           |
| POST   | `/facebook/publish-photo`     | Publish a photo with a caption (max 15 MB)          |
| POST   | `/facebook/disconnect`        | Disconnect the Facebook Page                        |

The `/auth` and `/chat` endpoints require an `Authorization: Bearer <Firebase ID token>` header.

## Roadmap

- Save Facebook Page connections per user in PostgreSQL. Right now one connection is kept in server memory and resets when the backend restarts.
- AI image generation for posts with Stable Diffusion XL (settings are already in place).
- Post scheduling and support for more platforms, such as Instagram and LinkedIn.

## Security

Never commit `backend/.env` or `firebase-service-account.json`. Both are listed in `backend/.gitignore`. If a key is ever pushed to GitHub by mistake, revoke it and create a new one right away.
