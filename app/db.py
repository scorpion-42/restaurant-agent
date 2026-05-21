"""DynamoDB operations for chat-history persistence.

Schema: primary key (user_uuid, created_at), one row per message. A user maps
to a single continuous timeline of messages — there is no conversation_id.
"""

import os
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "smashery-agent-chat-history")
REGION = os.environ.get("AWS_REGION", "us-east-2")

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_table = _dynamodb.Table(TABLE_NAME)
# transact_write_items lives only on the low-level client, reached via
# .meta.client. Because this client is attached to the Resource it auto-marshals
# raw Python types, so we pass plain dicts — not {"S": ...} attribute values.
_client = _dynamodb.meta.client


def _iso_format(ts: datetime) -> str:
    """Format a datetime as ISO 8601 with microsecond precision and a Z suffix."""
    return ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def save_turn(user_uuid: str, user_message: str, assistant_message: str) -> None:
    """Save user + assistant messages atomically as a single DynamoDB transaction.

    Both messages either succeed or fail together. The user message timestamp is
    captured first; the assistant timestamp is forced to be 1 microsecond later
    to guarantee chronological sort order within a pair.
    """
    base = datetime.now(timezone.utc)
    user_ts = _iso_format(base)
    assistant_ts = _iso_format(base + timedelta(microseconds=1))

    _client.transact_write_items(
        TransactItems=[
            {
                "Put": {
                    "TableName": TABLE_NAME,
                    "Item": {
                        "user_uuid": user_uuid,
                        "created_at": user_ts,
                        "role": "user",
                        "content": user_message,
                    },
                }
            },
            {
                "Put": {
                    "TableName": TABLE_NAME,
                    "Item": {
                        "user_uuid": user_uuid,
                        "created_at": assistant_ts,
                        "role": "assistant",
                        "content": assistant_message,
                    },
                }
            },
        ]
    )


def load_recent_messages(
    user_uuid: str,
    hours: int = 48,
    max_pairs: int = 20,
) -> list[dict[str, str]]:
    """Load recent messages for a user, capped by hours AND max_pairs.

    Returns chronologically ordered [{role, content}] suitable for Claude's
    messages parameter. The cap logic:
      - KeyCondition filters to created_at >= now - hours
      - Limit caps the count at max_pairs * 2 messages
      - Whichever cap is more restrictive is what gets returned
    Pair integrity holds as long as save_turn stays the only writer (each pair is
    two items written atomically, so the most recent 2N items are N full pairs).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_str = _iso_format(cutoff)

    response = _table.query(
        KeyConditionExpression=(
            Key("user_uuid").eq(user_uuid) & Key("created_at").gte(cutoff_str)
        ),
        ScanIndexForward=False,  # newest first, so Limit takes the most recent
        Limit=max_pairs * 2,
    )

    items = response.get("Items", [])
    items.reverse()  # back to chronological order for Claude

    return [
        {"role": item["role"], "content": item["content"]}
        for item in items
    ]


def load_all_messages(user_uuid: str) -> list[dict]:
    """Load ALL messages for a user in chronological order.

    Used by the frontend to render the full timeline on page load. Returns
    [{role, content, created_at}] so the frontend can use created_at for things
    like session-boundary detection if needed.
    """
    response = _table.query(
        KeyConditionExpression=Key("user_uuid").eq(user_uuid),
        ScanIndexForward=True,  # chronological order
    )
    items = response.get("Items", [])
    return [
        {
            "role": item["role"],
            "content": item["content"],
            "created_at": item["created_at"],
        }
        for item in items
    ]


def delete_message(user_uuid: str, created_at: str) -> bool:
    """Delete a single message by its full primary key. Returns True if it existed.

    Per-message deletion capability, NOT exposed via an HTTP endpoint in this
    deployment. May leave orphans (a user turn without its assistant or vice
    versa); callers handle any downstream effects.
    """
    response = _table.delete_item(
        Key={"user_uuid": user_uuid, "created_at": created_at},
        ReturnValues="ALL_OLD",
    )
    return "Attributes" in response


def delete_all_user_messages(user_uuid: str) -> int:
    """Delete all messages for a user; returns the count of deleted items.

    Used by the destructive "New Conversation" flow. batch_writer handles
    batching (up to 25 per request) and retries any unprocessed items.
    """
    response = _table.query(
        KeyConditionExpression=Key("user_uuid").eq(user_uuid),
    )
    items = response.get("Items", [])
    if not items:
        return 0

    with _table.batch_writer() as batch:
        for item in items:
            batch.delete_item(
                Key={
                    "user_uuid": item["user_uuid"],
                    "created_at": item["created_at"],
                }
            )
    return len(items)
