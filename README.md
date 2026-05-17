# Restaurant Q&A Agent

An HTTP API that answers customer questions about a restaurant — built with FastAPI and Claude, running serverless on AWS Lambda.

## Live demo

- **Live demo — chat UI:** https://cozedmff7xsjgd6plbpvkunnd40pypti.lambda-url.us-east-2.on.aws/
- **Live demo — Swagger UI:** https://cozedmff7xsjgd6plbpvkunnd40pypti.lambda-url.us-east-2.on.aws/docs
- **GitHub repo:** https://github.com/scorpion-42/restaurant-agent

## What it does

"The Smashery" is a fictional smash-burger restaurant. This service answers customer questions about it — menu items, hours, dietary options, and recommendations — by sending the question to Claude together with a system prompt that holds the restaurant's details. It replies in the language the customer used, so a question asked in Spanish gets a Spanish answer. It supports multi-turn conversations — you can ask follow-up questions and the agent maintains context within a session. The service exposes two interfaces — a web app at the root URL (a browsable menu with category filters, a restaurant-info tab, and a chat sidebar) and an interactive Swagger UI at `/docs` — both backed by the same `/chat` endpoint.

## Try it

Two ways to try it:

- **Chat UI:** open the [chat page](https://cozedmff7xsjgd6plbpvkunnd40pypti.lambda-url.us-east-2.on.aws/) and type a question.
- **Swagger UI:** open the [Swagger UI](https://cozedmff7xsjgd6plbpvkunnd40pypti.lambda-url.us-east-2.on.aws/docs), expand `POST /chat`, click **Try it out**, and send a JSON body like `{"messages": [{"role": "user", "content": "..."}]}`.

Some questions to try:

- `What time do you close on Saturday?`
- `Which burgers are vegetarian?`
- `I'm gluten-free — what are my options?`
- `I love spicy food. What do you recommend?`
- `What comes on the Bacon BBQ Stack?`
- `Can you help me debug my Python code?` — off-topic; watch it redirect back to restaurant questions
- `¿Tienen opciones veganas?` — Spanish; "Do you have vegan options?"

**Try a follow-up:** ask `Which burgers are vegetarian?`, then `What about for kids?` — the agent keeps the context from the first question.

## Architecture

```
Browser / HTTP client
        │  HTTPS
        ▼
AWS Lambda Function URL        public endpoint — no API Gateway
        │
        ▼
Mangum                         translates the Lambda event into ASGI
        │
        ▼
FastAPI  ──  POST /chat        request validation and routing
        │
        ▼
Anthropic API  ──  Claude Haiku 4.5
```

There is no database, no authentication, and no API Gateway — the Lambda Function URL is the public endpoint directly. The restaurant's menu and details are hardcoded in the system prompt, so there is no external data store.

## Stack

- **Python 3.12**
- **FastAPI** — web framework; serves the interactive Swagger UI at `/docs`
- **Mangum** — ASGI-to-Lambda adapter, so the FastAPI app runs as a Lambda function
- **Anthropic SDK** — calls Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- **AWS Lambda + Function URL** — serverless hosting (arm64, `us-east-2`)
- **uv** — Python package and environment management

## Run locally

```bash
# Clone the repo
git clone https://github.com/scorpion-42/restaurant-agent.git
cd restaurant-agent

# Add your Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Install dependencies
uv sync

# Start the dev server
uv run uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000/docs in your browser.

## Redeploy to AWS Lambda

```bash
./build.sh
```

This produces `deployment.zip`, with dependencies built for Linux arm64. Then, in the AWS Console:

1. Open **Lambda → `restaurant-agent` function → Code**.
2. Choose **Upload from → .zip file**, select `deployment.zip`, and save.

## Project structure

```
restaurant-agent/
├── app/
│   ├── __init__.py
│   ├── main.py            FastAPI app: POST /chat, request/response models, system prompt
│   └── lambda_handler.py  Mangum adapter — the Lambda entry point
├── build.sh               builds deployment.zip for AWS Lambda
└── pyproject.toml         project metadata and dependencies
```

## Notes

- "The Smashery" and its entire menu are fictional.
- Conversation history is multi-turn but client-managed — the backend stays stateless, and refreshing the page starts a new conversation.
- Menu data lives in the system prompt; updating the menu means editing `app/main.py` and redeploying.
