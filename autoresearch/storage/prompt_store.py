import os
from pathlib import Path
from typing import Optional

class PromptStore:
    """
    Manages the storage, versioning, and retrieval of prompt templates.
    Baseline prompts are read from the main project folder, while
    optimized champion prompts are stored inside autoresearch/prompts/.
    """
    def __init__(self, generator_prompt_path: str, prompts_dir: str):
        self.generator_prompt_path = Path(generator_prompt_path)
        self.prompts_dir = Path(prompts_dir)
        self._ensure_directories()

    def _ensure_directories(self):
        """Creates the prompts directory if it doesn't exist."""
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    def save_champion(self, version: int, full_prompt_content: str) -> Path:
        """
        Saves a new champion prompt with a version tag, and duplicates it as
        champion_latest.prompt.md inside the autoresearch/prompts/ folder.
        """
        # Save versioned file
        versioned_path = self.prompts_dir / f"champion_v{version}.prompt.md"
        with open(versioned_path, "w", encoding="utf-8") as f:
            f.write(full_prompt_content)
        
        # Save as latest
        latest_path = self.prompts_dir / "champion_latest.prompt.md"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(full_prompt_content)
            
        return versioned_path

    def get_latest_prompt_content(self) -> Optional[str]:
        """
        Retrieves the content of champion_latest.prompt.md if it exists,
        otherwise falls back to the original baseline prompt file.
        """
        latest_path = self.prompts_dir / "champion_latest.prompt.md"
        if latest_path.exists():
            with open(latest_path, "r", encoding="utf-8") as f:
                return f.read()
        
        if self.generator_prompt_path.exists():
            with open(self.generator_prompt_path, "r", encoding="utf-8") as f:
                return f.read()
                
        return None

    def get_prompt_path(self, version: int) -> Path:
        """Returns the path to a specific versioned champion prompt."""
        return self.prompts_dir / f"champion_v{version}.prompt.md"

    def get_latest_prompt_path(self) -> Path:
        """Returns the path to the latest champion prompt, falling back to the baseline path."""
        latest_path = self.prompts_dir / "champion_latest.prompt.md"
        if latest_path.exists():
            return latest_path
        return self.generator_prompt_path
