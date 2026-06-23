import requests

from app.openai_client import api_key


def create_realtime_token():
    response = requests.post(
        "https://api.openai.com/v1/realtime/client_secrets",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "session": {
                "type": "realtime",
                "model": "gpt-realtime-2",
                "audio": {
                    "output": {
                        "voice": "marin"
                    }
                }
            }
        }
    )

    response.raise_for_status()

    return response.json()