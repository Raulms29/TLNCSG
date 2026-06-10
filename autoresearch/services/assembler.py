import re
from typing import Tuple

class PromptAssembler:
    """
    Parses a prompt template, extracts the editable ## INSTRUCTIONS section,
    and merges updated instructions back with static parts (prefix, grammar, examples).
    """
    def __init__(self):
        pass

    def extract_instructions(self, full_prompt_content: str) -> Tuple[str, str, str]:
        """
        Splits the prompt content into prefix, instructions, and suffix.
        Returns:
            prefix: Static content before the ## INSTRUCTIONS heading.
            instructions: Content strictly inside ## INSTRUCTIONS (excluding headers).
            suffix: Static content after the instructions (usually starting with ## GRAMMAR).
        """
        # Search for "## INSTRUCTIONS" header (case insensitive, allowed spaces)
        instructions_match = re.search(r"##\s*INSTRUCTIONS\s*", full_prompt_content, re.IGNORECASE)
        if not instructions_match:
            raise ValueError("Could not find '## INSTRUCTIONS' section in the prompt template.")

        instructions_start = instructions_match.end()
        prefix = full_prompt_content[:instructions_match.start()]

        # The end of the instructions is marked by the next markdown header (e.g. ## GRAMMAR, ## EXAMPLES)
        # or a markdown separator like "---" followed by a header.
        remaining_content = full_prompt_content[instructions_start:]
        
        # Look for the next major header (## ) or separator followed by a header
        suffix_match = re.search(r"(?:^|\n)(?:---\s*\n)?##\s+", remaining_content)
        
        if suffix_match:
            instructions_end = suffix_match.start()
            instructions = remaining_content[:instructions_end].strip()
            # The suffix includes the matched separator/header and everything after
            suffix = remaining_content[instructions_end:].lstrip()
        else:
            # Fallback if no subsequent header is found (instructions extend to the end of the file)
            instructions = remaining_content.strip()
            suffix = ""

        return prefix, instructions, suffix

    def assemble_prompt(self, prefix: str, new_instructions: str, suffix: str) -> str:
        """
        Reassembles the prompt by sandwiching the new instructions between prefix and suffix.
        """
        # Clean up spacing to ensure clean separation
        prefix_clean = prefix.rstrip()
        instructions_clean = new_instructions.strip()
        suffix_clean = suffix.lstrip()
        
        # Build prompt
        assembled = f"{prefix_clean}\n\n## INSTRUCTIONS\n\n{instructions_clean}\n\n{suffix_clean}"
        return assembled
