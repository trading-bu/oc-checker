"""
Post a message to a Slack channel via Incoming Webhook.
Usage: python post_slack.py <payload_json_string_or_file>
"""

import json
import sys
import urllib.request


def post(webhook_url: str, payload: dict) -> bool:
    """Post payload to Slack webhook. Returns True on success."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return resp.status == 200 and body == "ok"
    except Exception as e:
        print(f"Slack post failed: {e}", file=sys.stderr)
        return False


def post_text(webhook_url: str, text: str) -> bool:
    """Post plain text to Slack."""
    return post(webhook_url, {"text": text})


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python post_slack.py <webhook_url> <message_text_or_json_file>")
        sys.exit(1)

    webhook = sys.argv[1]
    arg = sys.argv[2]

    # Try as JSON file first, then as plain text
    try:
        with open(arg) as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        payload = {"text": arg}

    ok = post(webhook, payload)
    if ok:
        print("Message sent to Slack successfully.")
    else:
        print("Failed to send Slack message.", file=sys.stderr)
        sys.exit(1)
