"""AgentCore Runtime entrypoint for the FinWise harness."""
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agents import run_harness
from tools import record_outcome

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Two operations: run the harness for a client, or record an advisor outcome.

    {"client_id": "C-1001", "advisor_id": "A-7"}
    {"op": "record_outcome", "client_id": "C-1001", "card_id": "...", "action": "not_now"}
    """
    if payload.get("op") == "record_outcome":
        return record_outcome(payload["client_id"], payload["card_id"],
                              payload["action"], payload.get("note", ""))
    return run_harness(payload["client_id"], payload.get("advisor_id"),
                       with_briefs=payload.get("with_briefs", True))


if __name__ == "__main__":
    app.run()
