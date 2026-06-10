import sys
import os
import json
import signal
import time

# Add project root to path to resolve absolute imports correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from autoresearch.core import Query, Experiment
from autoresearch.storage import PromptStore, ExperimentLogger
from autoresearch.services import (
    PromptAssembler,
    GeneratorClient,
    EvaluatorAgent,
    OptimizerAgent,
    ValidationRunner,
)

# Global variables for Unix signal handling
graceful_stop = False
ctrl_c_count = 0


def signal_handler(signum, frame):
    global graceful_stop, ctrl_c_count
    ctrl_c_count += 1
    if ctrl_c_count == 1:
        print("\n[Termination Triggered] SIGINT/SIGTERM received.")
        print(
            "Finishing the current iteration and exiting gracefully. Press Ctrl+C again to force stop."
        )
        graceful_stop = True
    else:
        print("\n[Forced Stop] Second interrupt received. Exiting immediately.")
        sys.exit(1)


# Register signal handlers for Linux VM execution
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    global graceful_stop

    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found at {config_path}")
        sys.exit(1)

    config = load_config(config_path)

    # 1. Initialize Storage layers
    prompt_store = PromptStore(
        generator_prompt_path=config["paths"]["generator_prompt"],
        prompts_dir=config["paths"]["prompts_dir"],
    )

    log_path = os.path.join(os.path.dirname(__file__), "experiments.json")
    logger = ExperimentLogger(log_path)

    # 2. Initialize Ollama wrapper clients
    ollama_url = config["ollama_server"]

    generator = GeneratorClient(
        ollama_url=ollama_url,
        model_name=config["generator"]["model"],
        temperature=config["generator"]["temperature"],
        num_ctx=config["generator"]["num_ctx"],
        num_predict=config["generator"]["num_predict"],
    )

    evaluator = EvaluatorAgent(
        ollama_url=ollama_url,
        model_name=config["evaluator"]["model"],
        temperature=config["evaluator"]["temperature"],
        num_ctx=config["evaluator"]["num_ctx"],
        num_predict=config["evaluator"]["num_predict"],
        prompt_path=config["paths"]["evaluator_prompt"],
    )

    optimizer = OptimizerAgent(
        ollama_url=ollama_url,
        model_name=config["optimizer"]["model"],
        temperature=config["optimizer"]["temperature"],
        num_ctx=config["optimizer"]["num_ctx"],
        num_predict=config["optimizer"]["num_predict"],
        memory_size=config["optimizer"]["failure_memory_size"],
        prompt_path=config["paths"]["optimizer_prompt"],
    )

    # 3. Initialize Domain services
    runner = ValidationRunner(
        ground_truths_path=config["paths"]["ground_truths"],
        generator=generator,
        evaluator=evaluator,
        runs_per_query=config["generator"].get("runs_per_query", 1),
    )

    assembler = PromptAssembler()

    # 4. Check status and initialize loop variables
    history = logger.load_history()
    iteration = logger.get_next_iteration_number()
    best_exp = logger.get_best_experiment()

    # Determine active champion and its score
    if best_exp:
        champion_score = best_exp.score
        active_failures = best_exp.failures
        print(f"Resuming optimization loop from iteration #{iteration}.")
        print(
            f"Current champion established at iteration #{best_exp.iteration} with Score: {champion_score:.4f}"
        )
        champion_content = prompt_store.get_latest_prompt_content()
        if not champion_content:
            print("Error: Resuming history but latest champion file not found.")
            sys.exit(1)
        prefix, champion_instructions, suffix = assembler.extract_instructions(
            champion_content
        )
    else:
        # First-time run: evaluate the baseline prompt to set a starting score
        print("Initializing autoresearch loop. Evaluating baseline prompt...")
        baseline_content = prompt_store.get_latest_prompt_content()
        if not baseline_content:
            print("Error: Baseline prompt could not be loaded.")
            sys.exit(1)

        prefix, champion_instructions, suffix = assembler.extract_instructions(
            baseline_content
        )
        baseline_prompt = assembler.assemble_prompt(
            prefix, champion_instructions, suffix
        )

        # Evaluate baseline
        score, failures = runner.run_validation(baseline_prompt)
        champion_score = score
        active_failures = failures

        # Save baseline as version 1 champion
        version_path = prompt_store.save_champion(1, baseline_prompt)

        initial_exp = Experiment(
            iteration=1,
            score=score,
            delta=0.0,
            status="CHAMPION_INIT",
            prompt_path=str(version_path),
            failures=failures,
        )
        logger.log_experiment(initial_exp)

        print(
            f"Baseline established. Score: {score:.4f}. Logs written to experiments.json."
        )

        # We start optimization loop at iteration 2
        iteration = 2

        # If the baseline is already perfect, we stop
        if score >= config["loop_settings"]["target_score"]:
            print("Target score reached during baseline check. Stopping.")
            sys.exit(0)

    # 5. Main Optimization Loop
    max_iter = config["loop_settings"]["max_iterations"]
    target_score = config["loop_settings"]["target_score"]

    print("\nEntering optimization loop...")
    while True:
        # Check iteration limit (if max_iterations is not -1)
        if max_iter != -1 and iteration > max_iter:
            print(
                f"Reached maximum configured iterations ({max_iter}). Stopping optimization."
            )
            break

        # Check Linux graceful stop flag
        if graceful_stop:
            print("Graceful stop flagged. Exiting loop cleanly.")
            break

        print(f"\n=========================================")
        print(f"STARTING ITERATION #{iteration}")
        print(f"=========================================")
        print(f"Current Champion Score: {champion_score:.4f}")
        print(f"Failing queries to fix: {len(active_failures)}")

        # 1. Invoke Optimizer to propose refinements
        print("Calling Optimizer Agent to refine instructions...")
        try:
            new_instructions = optimizer.optimize_instructions(
                current_instructions=champion_instructions, failures=active_failures
            )
        except Exception as e:
            print(
                f"Optimization Error: Failed to generate optimized instructions: {str(e)}"
            )
            print("Skipping iteration due to LLM error.")
            time.sleep(5)
            continue

        # 2. Assemble candidate prompt
        candidate_prompt = assembler.assemble_prompt(prefix, new_instructions, suffix)

        # 3. Evaluate candidate prompt over the validation dataset
        candidate_score, candidate_failures = runner.run_validation(candidate_prompt)

        delta = candidate_score - champion_score
        print(f"Candidate Score: {candidate_score:.4f} (Delta: {delta:+.4f})")

        # 4. Apply Keep / Discard decision
        if delta > 0:
            print(">>> SUCCESS: Score improved! Saving new champion prompt.")
            status = "KEEP"

            # Persist champion files in storage
            version_path = prompt_store.save_champion(iteration, candidate_prompt)

            # Reset failure memory and update champion state
            optimizer.clear_failure_history()
            champion_instructions = new_instructions
            champion_score = candidate_score
            active_failures = candidate_failures
        else:
            print(">>> FAILURE: Score did not improve. Discarding changes.")
            status = "DISCARDED"
            version_path = prompt_store.get_latest_prompt_path()

            # Feed the optimizer memory with this rejected attempt
            optimizer.add_to_failure_history(
                score=candidate_score, instructions=new_instructions
            )

        # 5. Log experiment iteration
        exp_record = Experiment(
            iteration=iteration,
            score=candidate_score,
            delta=delta,
            status=status,
            prompt_path=str(version_path),
            failures=candidate_failures,
        )
        logger.log_experiment(exp_record)
        print(f"Iteration #{iteration} logged successfully to experiments.json.")

        # 6. Check target termination score
        if champion_score >= target_score:
            print(
                f"\nTarget validation score ({target_score}) reached! Stopping optimization."
            )
            break

        iteration += 1

    print("\nOptimization process completed.")
    best_overall = logger.get_best_experiment()
    if best_overall:
        print(
            f"Best prompt found at iteration #{best_overall.iteration} with Score: {best_overall.score:.4f}"
        )


if __name__ == "__main__":
    main()
