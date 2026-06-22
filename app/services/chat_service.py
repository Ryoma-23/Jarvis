import json

from datetime import datetime

from app.config import SYSTEM_PROMPT_PATH
from app.openai_client import client
from app.services.intent_service import (
    handle_note_intent,
    handle_task_intent,
    handle_memory_intent
)
from app.services.memory_service import format_memory_for_prompt


conversation_history = []

MAX_HISTORY = 30


def trim_history():
    global conversation_history

    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]


def load_system_prompt():
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as file:
        return file.read()


def generate_chat_stream(message: str):

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")

        current_datetime_message = {
            "role": "system",
            "content": f"現在日時: {current_time}"
        }

        note_reply = handle_note_intent(message)

        if note_reply is not None:
            yield f"data: {json.dumps({'text': note_reply})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        task_reply = handle_task_intent(message)

        if task_reply is not None:
            yield f"data: {json.dumps({'text': task_reply})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        memory_reply = handle_memory_intent(message)

        if memory_reply is not None:
            yield f"data: {json.dumps({'text': memory_reply})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        conversation_history.append({
            "role": "user",
            "content": message
        })

        trim_history()

        system_prompt = load_system_prompt()

        memory_context = format_memory_for_prompt()

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            current_datetime_message,
            {
                "role": "system",
                "content": memory_context
            }
        ] + conversation_history

        full_reply = ""

        stream = client.responses.create(
            model="gpt-5-mini",
            input=messages,
            stream=True,
            reasoning={"effort": "low"},
        )

        for event in stream:
            if event.type == "response.output_text.delta":
                text = event.delta
                full_reply += text

                yield f"data: {json.dumps({'text': text})}\n\n"

        conversation_history.append({
            "role": "assistant",
            "content": full_reply
        })

        trim_history()

        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"