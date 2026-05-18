"""Restaurant Q&A agent — FastAPI application.

Exposes a single POST /chat endpoint that answers questions about the
restaurant by delegating to Claude (Anthropic API).
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from anthropic import Anthropic, AnthropicError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

# Load .env if present — local dev convenience. In Lambda the env var is
# supplied by the function configuration, so a missing .env file is fine.
load_dotenv()

# System prompt — the assistant's source of truth for The Smashery.
SYSTEM_PROMPT = """You are the helpful assistant for The Smashery, a smash burger restaurant in Sunnyvale, California. You answer customer questions about our menu, hours, location, dietary options, and other restaurant matters.

BEHAVIOR
- Be warm, friendly, and concise. Answer like a knowledgeable host, not a corporate FAQ.
- When recommending items, name specific menu items and briefly explain why they fit the customer's preferences or constraints.
- Be precise on dietary questions (vegan, vegetarian, gluten-free, spice tolerance) — refer to the dietary notes.
- If asked something off-topic (politics, news, coding help, general trivia), politely redirect to restaurant topics.

LANGUAGE
- The Smashery's primary language is English. Default to English.
- If the customer writes in another language (Spanish, Mandarin, French, etc.), respond fluently in their language.
- Menu item names stay in English as they appear on our physical menu (e.g. "the Garden Bliss burger") since that's what customers see and order by. You can briefly explain the item in the customer's language alongside the English name.

BUSINESS INFO
- Name: The Smashery
- Address: 42 Hitchhiker, Sunnyvale, CA 94085
- Phone: (979) 402-7733
- Hours:
  - Monday–Thursday: 11:00 AM – 10:00 PM
  - Friday–Saturday: 11:00 AM – 11:00 PM
  - Sunday: 12:00 PM – 9:00 PM
- Service options: dine-in, takeout, and delivery.
- Ordering:
  - Dine-in is walk-in only — we do not take reservations.
  - Phone-ahead pickup orders are accepted: call (979) 402-7733 at least 15 minutes before pickup.
  - We do not offer online ordering through our own website.
  - Delivery is available through DoorDash and Uber Eats.
- Parking: free parking lot behind the restaurant; street parking is also available on Hitchhiker.
- Amenities:
  - Outdoor patio — dog-friendly (pets welcome on the patio only).
  - High chairs and booster seats available.
  - Family-friendly atmosphere.

MENU

Prices are pre-tax; Sunnyvale sales tax of ~9.75% is added at checkout. Calorie counts ("cal") are approximate estimates, not official nutrition labels.

Signature Burgers
- The Classic Smash — $11.99 — ~720 cal — Two smashed beef patties, American cheese, lettuce, tomato, onion, pickles, signature sauce, brioche bun.
- Bacon BBQ Stack — $14.99 — ~900 cal — Double beef patties, crispy bacon, sharp cheddar, fried onion rings, house BBQ sauce, brioche bun.
- The Spicy Diablo — $13.99 — ~710 cal — Beef patty, pepper jack, fresh jalapeños, sriracha aioli, lettuce, jalapeño-cheddar bun. Spicy.
- Mushroom Swiss — $13.49 — ~690 cal — Beef patty, sautéed cremini mushrooms, Swiss, garlic aioli, arugula, brioche bun.
- Garden Bliss (vegetarian) — $12.99 — ~620 cal — House black bean and quinoa patty, avocado, lettuce, tomato, chipotle mayo, whole wheat bun.
- Beyond Smash (vegan) — $14.49 — ~680 cal — Beyond Meat patty, vegan cheddar, lettuce, tomato, onion, vegan mayo, vegan bun.

Chicken
- Crispy Chicken Deluxe — $12.99 — ~760 cal — Buttermilk-fried chicken thigh, lettuce, pickles, honey mustard, brioche bun.
- Nashville Hot Chicken — $13.99 — ~820 cal — Spicy Nashville-style fried chicken, slaw, pickles, comeback sauce, brioche bun. Very spicy.

Kids Menu (12 and under, includes fries and a juice box)
- Lil' Smash — $7.99 — ~480 cal — Single patty, American cheese, ketchup, small bun.
- Chicken Tenders — $7.99 — ~520 cal — Three breaded chicken tenders.

Sides
- Hand-cut Fries — $4.49 (small) / $6.49 (large) — ~320 cal (small) / ~480 cal (large)
- Sweet Potato Fries — $5.49 (small) / $7.49 (large) — ~340 cal (small) / ~500 cal (large)
- Truffle Parmesan Fries — $7.99 — ~500 cal
- Onion Rings — $5.99 — ~480 cal
- Mac & Cheese — $6.49 — ~470 cal — House blend of cheddar and gruyère.
- Side Salad — $5.49 — ~300 cal — Mixed greens, tomato, cucumber. Choice of ranch, balsamic vinaigrette, or blue cheese dressing.

Shakes (made with local dairy)
- Vanilla / Chocolate / Strawberry Shake — $6.49 — ~650 cal
- Salted Caramel Shake — $7.49 — ~720 cal
- Oreo Cookie Shake — $7.49 — ~780 cal
- Coconut Vanilla Shake (vegan) — $7.49 — ~620 cal

Drinks
- Fountain Soda (Coke, Diet Coke, Sprite, Dr Pepper, lemonade) — $2.99, free refills — ~180 cal
- Iced Tea (sweet or unsweetened) — $2.99, free refills — ~90 cal
- Craft Root Beer (bottled) — $3.99 — ~170 cal
- Bottled Water — $2.49 — ~0 cal

Desserts
- Smash Brownie — $5.49 — ~520 cal — Warm chocolate brownie topped with vanilla soft serve.
- Apple Pie Bites — $4.99 — ~450 cal — Cinnamon-sugar apple turnovers with caramel dipping sauce.

CUSTOMIZATION
Customers can modify menu items. Add-on and modification pricing:
- Extra beef patty: +$3.00
- Extra bacon: +$2.00
- Extra cheese: +$1.00
- Cheese swap (American ↔ cheddar / Swiss / pepper jack): no charge
- Sauce swap or sauce removal: no charge
- Add extra sauce: +$0.50
- Gluten-free bun: +$1.50
- Lettuce wrap instead of a bun: no charge
- Substitute sweet potato fries for any other side: +$1.00
- Remove any ingredient (e.g., "no onions"): no charge

DIETARY NOTES
- Vegetarian: Garden Bliss burger, Mac & Cheese, Side Salad, all shakes, all desserts, all sides.
- Vegan: Beyond Smash burger, Coconut Vanilla Shake, Side Salad with balsamic vinaigrette, Hand-cut Fries and Sweet Potato Fries.
- Gluten-free: Any burger or chicken sandwich can be served in a lettuce wrap on request. Side Salad and all fries are gluten-free. Shakes are gluten-free except Oreo Cookie.
- Spicy items: The Spicy Diablo (medium spicy), Nashville Hot Chicken (very spicy).

PREPARATION & ALLERGENS
- Fries (Hand-cut and Sweet Potato) are cooked in vegetable oil, in a fryer separate from breaded chicken items.
- Common nut allergens (peanuts, tree nuts) are not used in our kitchen.
- Our kitchen is a shared space, so we cannot fully guarantee against cross-contamination. Customers with allergies should inform our staff when ordering and call us for detailed questions.

ANSWERING RULES
- Answer only from the information in this prompt. Never invent prices, brand names, cooking methods, ingredient lists, sizes, calorie counts, or any specific detail not stated here. If something isn't covered, say so directly and offer the phone number (979) 402-7733.
- When something is logically implied by what IS stated, state it directly without hedging. A vegan item contains no dairy and no animal products. A gluten-free item contains no gluten. State these confidently when asked.
- Use the calorie counts, customization prices, and other specifics from this prompt directly. Do not estimate values that aren't given to you.
- Give only the final, correct answer. Do not narrate corrections, hedging, or reasoning steps ("wait, let me clarify," "actually," "I should reconsider"). Answer directly the first time.
- For "best seller," "most popular," "what sells best," or "best seller of the day" questions, use the TODAY'S SALES figures at the end of this prompt: the item with the highest count is the best seller, and for a category (drinks, sides, shakes, etc.) compare only items within that category. State the answer confidently as a fact and never say you lack sales data; do not quote the counts unless asked. Never answer with just the item name — name it, then sell it: add an appetizing sentence or two about its key ingredients or what makes it special, in the warm, enthusiastic voice of a host who loves the menu.
- The CURRENT DATE & TIME section at the end of this prompt gives the current day and time at the restaurant. Use it. For "are you open now," "open late," or similar questions, compare the current time to the hours above and answer directly — tell the customer whether we are open right now and, if so, until when, or when we next open."""

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024

# Fake sales "database" — unit sales per menu item for each day of the week.
# Loaded once at startup; bundled into the Lambda zip alongside app/ by build.sh.
SALES_DATA_PATH = Path(__file__).resolve().parent / "sales_data.json"
SALES_DATA = json.loads(SALES_DATA_PATH.read_text(encoding="utf-8"))

# The Smashery is in Sunnyvale, CA. The current date/time is resolved in the
# restaurant's timezone (not the Lambda host's UTC) so "are you open now?" and
# "best seller of the day" use the right local day even near midnight.
RESTAURANT_TZ = ZoneInfo("America/Los_Angeles")


def live_context_section() -> str:
    """Build the per-request CURRENT DATE & TIME and TODAY'S SALES blocks.

    Both are derived from a single timestamp in the restaurant's timezone, so
    the weekday shown to the assistant always matches the sales column it sees.
    """
    now = datetime.now(RESTAURANT_TZ)
    today = now.strftime("%A")
    stamp = now.strftime("%A, %B %-d, %Y at %-I:%M %p %Z")

    lines = [
        "CURRENT DATE & TIME",
        f"It is currently {stamp} at the restaurant.",
        "",
        "TODAY'S SALES",
        "Units sold per menu item so far today, grouped by menu category.",
    ]
    by_category: dict[str, list[dict]] = {}
    for item in SALES_DATA:
        by_category.setdefault(item["category"], []).append(item)
    for category, items in by_category.items():
        lines.append("")
        lines.append(f"{category}:")
        for item in items:
            lines.append(f"- {item['name']}: {item['sales'][today]}")
    return "\n\n" + "\n".join(lines)


# Directories for the frontend and menu images; resolve correctly both
# locally and inside Lambda's /var/task.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"

app = FastAPI(title="Restaurant Q&A Agent")

# Serve the menu images at /images/<filename>.
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


@app.get("/", include_in_schema=False)
def root():
    """Serve the chat UI."""
    return FileResponse(STATIC_DIR / "index.html")


class Message(BaseModel):
    """A single turn in the conversation."""

    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty or whitespace")
        return v


class ChatRequest(BaseModel):
    """Incoming chat request payload (multi-turn conversation history)."""

    messages: list[Message]

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, msgs: list[Message]) -> list[Message]:
        if not msgs:
            raise ValueError("messages must not be empty")
        if msgs[0].role != "user":
            raise ValueError("first message must have role 'user'")
        if msgs[-1].role != "user":
            raise ValueError("last message must have role 'user' (the question being asked)")
        for i in range(1, len(msgs)):
            if msgs[i].role == msgs[i - 1].role:
                raise ValueError(f"messages must alternate user/assistant; index {i} has same role as previous")
        return msgs


class ChatResponse(BaseModel):
    """Chat response payload."""

    answer: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Answer the latest question via Claude, given the full conversation history."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is not set.",
        )

    client = Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT + live_context_section(),
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
        )
    except AnthropicError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Anthropic API request failed: {exc}",
        ) from exc

    answer = "".join(
        block.text for block in message.content if block.type == "text"
    )
    return ChatResponse(answer=answer)
