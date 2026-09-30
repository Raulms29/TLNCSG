## Introduction
The systems or grammars to evaluate are SemGIR, SQUALL, and GraphQ IR. The objective is to evaluate the capacity of Large Language Models to translate queries into an intermediate representation, their clustering, automatic evaluation, and subsequent manual review.

## Technological Stack and Environment
*   **Base Language:** Python 3.14
*   **LLM Interaction:** Ollama API
*   **Data Management:** `pandas`, CSV and JSON formats.
*   **Manual Review:** Simple web application with Streamlit
*   **Development Environment:**
    *   The code will be executed in a **Docker container over WSL**.
    *   *Configuration Note:* It is highly recommended to switch to using `docker-compose` to orchestrate this. It will allow easy mapping of persistence volumes (`outputs` folder) to the WSL/Windows file system and cleanly expose the Streamlit UI port (e.g., `8501:8501`).
*   **Object-Oriented Modular Design (OOP):**
    *   It is proposed to abstract the logic into robust structural classes. For example, an `OllamaClient` class to centralize the connection, state management, and retries to the API, shared among the scripts; and specific classes like `DatasetManager` and `QueryExecutor` to abstract data loading and orchestration, respectively.

## Complementary Study: Ablation
Once the main pipeline is completely built and refined, secondary passes will be executed to perform an ablation study. This study does not require modifying the architecture, but rather injecting different configurations into Module 1.

**Variations to test (Ablation Study):**
1.  **Reduction of Expressiveness:** Execute SemGIR core vs SemGIR full to evaluate the hypothesis that increasing the expressiveness of an intermediate representation does not increase the parsing difficulty for LLMs.
2.  **Elimination of Semantic Annotations:** Modify the System Prompt to remove them.
3.  **Deactivation of Auto-optimization:** Flat evaluation without refinement routines.
4.  **Suppression of Prompts Structures:** Elimination of *Chain-of-Thought* elements or *few-shot* examples to measure the zero-shot resilience of the model.
