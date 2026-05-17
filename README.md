# Restaurant Q&A Agent

An HTTP API that answers customer questions about a restaurant — built with FastAPI and Claude, running serverless on AWS Lambda.

## Live demo

- **Live API (Swagger UI):** https://cozedmff7xsjgd6plbpvkunnd40pypti.lambda-url.us-east-2.on.aws/docs
- **GitHub repo:** https://github.com/scorpion-42/restaurant-agent

## What it does

"The Smashery" is a fictional smash-burger restaurant. This service answers customer questions about it — menu items, hours, dietary options, and recommendations — by sending the question to Claude together with a system prompt that holds the restaurant's details. It replies in the language the customer used, so a question asked in Spanish gets a Spanish answer. Each request is single-turn: there is no conversation memory between calls.

## Try it

Open the [Swagger UI](https://cozedmff7xsjgd6plbpvkunnd40pypti.lambda-url.us-east-2.on.aws/docs), expand `POST /chat`, click **Try it out**, and send a JSON body like `{"question": "..."}`. Some questions to try:

- `What time do you close on Saturday?`
- `Which burgers are vegetarian?`
- `I'm gluten-free — what are my options?`
- `I love spicy food. What do you recommend?`
- `What comes on the Bacon BBQ Stack?`
- `Can you help me debug my Python code?` — off-topic; watch it redirect back to restaurant questions
- `¿Tienen opciones veganas?` — Spanish; "Do you have vegan options?"

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
- Q&A is single-turn by design — the service keeps no conversation history.
- Menu data lives in the system prompt; updating the menu means editing `app/main.py` and redeploying.
