# TB Isolation Chatbot

This project contains a Node.js backend that talks to OpenAI and a React front-end in the `frontend/` folder. The frontend sends chat requests to `http://localhost:3001/api/chat`, so the backend must be running before you open the app.

## Prerequisites

- Node.js 18+
- npm
- An OpenAI API key
- An OpenAI prompt ID and vector store ID for the TB workflow

## 1) Configure environment variables

Create a `.env` file in the project root (or use the `backend/.env.example` template as a reference) with the following values:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_PROMPT_ID=your_prompt_id
OPENAI_VECTOR_STORE_ID=your_vector_store_id
PORT=3001
```

If you are using the `backend` folder directly, copy the example file:

```bash
cd backend
copy .env.example .env
```

Then edit the copied `.env` file and fill in the values.

## 2) Install dependencies

From the repository root:

```bash
npm install
```

Or, if you are running the backend from the `backend` directory:

```bash
cd backend
npm install
```

## 3) Start the backend

From the repo root:

```bash
npm start
```

Or from the backend folder:

```bash
cd backend
npm start
```

This starts the Express server on:

```text
http://localhost:3001
```

The app exposes the chat endpoint at:

```text
http://localhost:3001/api/chat
```

## 4) Start the frontend

The repo includes the React source files in `frontend/`, but it does not include a full frontend package setup. If you want to run the UI locally, initialize a small React/Vite app from that folder and serve it:

```bash
cd frontend
npm init -y
npm install react react-dom vite
npx vite --host
```

Then open the local URL shown in the terminal (usually `http://localhost:5173`) in your browser.

Important: keep the backend running on port 3001 while using the frontend.

## Common issues

- If the backend fails to start, make sure `.env` contains valid `OPENAI_API_KEY`, `OPENAI_PROMPT_ID`, and `OPENAI_VECTOR_STORE_ID` values.
- If the UI cannot send messages, confirm the backend is running and that the frontend is hitting `http://localhost:3001/api/chat`.
- If you see CORS errors, make sure the backend is running with `cors` enabled and that the frontend is not pointing to a different port.

## Project notes

- The backend is the main executable application for the chat API.
- The frontend is a separate UI layer that calls the backend API.
- The app is designed for the TB isolation workflow and uses the OpenAI vector store for retrieval.
