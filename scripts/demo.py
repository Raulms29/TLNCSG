import os
import sys
import json

# Project root is always resolved from this file's location, regardless of CWD
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)  # Ensure relative paths in imports resolve from the project root

from utils import load_prompt_file, build_chat_messages, _extract_json_text
from config import OLLAMA_SERVER
from ollama import Client

# ── Queries to run ────────────────────────────────────────────────────────────
QUERIES = [
    {
        "id": "Q40",
        "text": "Tell me the scientists who were students of Planck in 1907.",
    },
    {
        "id": "Q04",
        "text": "Give me the communication routes between the server with ID 'SR45' and any server at the University of Oviedo.",
    },
]

MODEL_NAME = "gemma4:26b"  # Ollama model name
# ──────────────────────────────────────────────────────────────────────────────


def format_json(obj, indent=2, level=0, max_inline=40):
    """Compact-smart JSON formatter: keeps short structures on one line."""
    space = " " * (indent * level)

    if not isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)

    if isinstance(obj, dict):
        inline = (
            "{"
            + ", ".join(
                f"{json.dumps(k)}: {format_json(v, indent, 0, max_inline)}"
                for k, v in obj.items()
            )
            + "}"
        )
        if "\n" not in inline and len(inline) <= max_inline:
            return inline
        lines = ["{"]
        items = list(obj.items())
        for i, (k, v) in enumerate(items):
            value = format_json(v, indent, level + 1, max_inline)
            comma = "," if i < len(items) - 1 else ""
            lines.append(
                " " * (indent * (level + 1)) + f"{json.dumps(k)}: {value}{comma}"
            )
        lines.append(space + "}")
        return "\n".join(lines)

    # List
    inline = "[" + ", ".join(format_json(x, indent, 0, max_inline) for x in obj) + "]"
    if "\n" not in inline and len(inline) <= max_inline:
        return inline
    lines = ["["]
    for i, x in enumerate(obj):
        value = format_json(x, indent, level + 1, max_inline)
        comma = "," if i < len(obj) - 1 else ""
        lines.append(" " * (indent * (level + 1)) + value + comma)
    lines.append(space + "]")
    return "\n".join(lines)


def main():
    # Initialize the Ollama client with the IP defined in config.py
    print(f"Server: {OLLAMA_SERVER}")
    ollama_client = Client(OLLAMA_SERVER)

    queries = QUERIES

    # Path to the SemGIR-APO prompt
    prompt_path = os.path.join(
        ROOT_DIR, "prompts", "grammars", "SYSTEM_PROMPT_SEM_GIR.prompt.md"
    )

    # Inference options matching model_eval.py configuration
    ollama_options = {
        "num_predict": 3072,
        "num_ctx": 12288,
    }

    system_prompt = load_prompt_file(prompt_path)

    output_dir = os.path.join(ROOT_DIR, "outputs", "demo")
    os.makedirs(output_dir, exist_ok=True)

    md_path = os.path.join(output_dir, "results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Demo\n\n")

        for idx, q in enumerate(queries, 1):
            print(f"\n[{idx}/{len(queries)}] {q['id']}: {q['text']}")
            print("─" * 60)
            f.write(f"## Query {q['id']}\n\n")
            f.write(f"##### {q['text']}\n\n")

            try:
                messages = build_chat_messages(system_prompt, q["text"])
                options = {**ollama_options, "temperature": 0.0}

                raw_response = ""
                # Stream tokens and print them in real time
                try:
                    for chunk in ollama_client.chat(
                        model=MODEL_NAME,
                        messages=messages,
                        stream=True,
                        options=options,
                        think=False,
                    ):
                        token = chunk["message"]["content"]
                        raw_response += token
                        print(token, end="", flush=True)
                except Exception as e:
                    print(f"\n[Error de conexión con Ollama: {e}]")
                    sys.exit(1)

                print()  # newline after stream ends

                # Format the JSON specifically for the markdown file
                clean_json_str = _extract_json_text(raw_response)
                try:
                    parsed = json.loads(clean_json_str)
                    formatted_json = format_json(parsed)
                except Exception:
                    formatted_json = clean_json_str
                    print("\n[warning: invalid JSON]")

                f.write(f"```json\n{formatted_json}\n```\n\n")

            except Exception as e:
                f.write(f"> ERROR: {e}\n\n")
                print(f"error: {e}")

    print(f"Saved to {md_path}")


if __name__ == "__main__":
    main()
