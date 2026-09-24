import json
import re

def _extract_json_text(text: str) -> str:
    """Extract JSON content, preferring the last fenced ```json block or last balanced curly brace structure when present."""
    if text is None:
        return ""
    text_str = str(text).strip()
    
    # 1. Try to find all markdown blocks and evaluate the last one
    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text_str, re.IGNORECASE)
    if blocks:
        for block in reversed(blocks):
            cleaned = block.strip()
            if (cleaned.startswith("{") and cleaned.endswith("}")) or (cleaned.startswith("[") and cleaned.endswith("]")):
                try:
                    json.loads(cleaned)
                    return cleaned
                except Exception:
                    pass
        # Fallback to the last markdown block if parsing failed
        return blocks[-1].strip()

    # 2. If no valid markdown block found, find balanced braces starting from the end
    end_idx = text_str.rfind("}")
    if end_idx != -1:
        brace_count = 0
        for i in range(end_idx, -1, -1):
            char = text_str[i]
            if char == "}":
                brace_count += 1
            elif char == "{":
                brace_count -= 1
                if brace_count == 0:
                    candidate = text_str[i:end_idx + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except Exception:
                        pass

    # 3. Fallback to original regex behavior or text strip
    match = re.search(
        r"```(?:json)?\s*(.*?)\s*```", text_str, flags=re.IGNORECASE | re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return text_str
