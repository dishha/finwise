"""FinWise dashboard backend: thin proxy over the AgentCore harness.
Env: HARNESS_ARN, AWS_REGION=ca-central-1.  pip install flask boto3 && python backend.py
"""
import json, os, uuid, re
import boto3
from flask import Flask, jsonify, request

HARNESS_ARN = os.environ["HARNESS_ARN"]
client = boto3.client("bedrock-agentcore", region_name=os.environ.get("AWS_REGION", "ca-central-1"))
app = Flask(__name__, static_folder="static", static_url_path="")


def invoke(text: str) -> dict:
    resp = client.invoke_harness(
        harnessArn=HARNESS_ARN,
        runtimeSessionId=f"finwise-{uuid.uuid4()}",
        messages=[{"role": "user", "content": [{"text": text}]}],
    )
    # Collect final text from the streamed/aggregated response, then parse the JSON object.
    chunks = []
    for ev in resp.get("stream", resp.get("response", [])):
        if isinstance(ev, dict):
            for blk in ev.get("message", {}).get("content", []) or []:
                if "text" in blk:
                    chunks.append(blk["text"])
    text_out = "".join(chunks) or json.dumps(resp, default=str)
    m = re.search(r"\{.*\}", text_out, re.S)
    return json.loads(m.group(0)) if m else {"raw": text_out}


@app.get("/api/book/<advisor_id>")
def book(advisor_id):
    return jsonify(invoke(f"Run the harness for advisor_id {advisor_id}. Return cards for every client in the book."))


@app.get("/api/brief/<advisor_id>/<client_id>")
def brief(advisor_id, client_id):
    return jsonify(invoke(f"Run the harness for advisor_id {advisor_id}, client_id {client_id} only, with a full brief."))


@app.post("/api/outcome")
def outcome():
    b = request.get_json()
    return jsonify(invoke(f"Record an advisor outcome: client_id {b['client_id']}, card_id {b['card_id']}, "
                          f"action {b['action']}, note: {b.get('note','')}. Call record_outcome and confirm."))


if __name__ == "__main__":
    app.run(port=5000, debug=True)
