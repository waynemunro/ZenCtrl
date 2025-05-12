# GitHub Copilot Working Principles for ZenCtrl Project

This document outlines the agreed-upon working principles and development strategy for the ZenCtrl project, specifically for the collaboration between the User and GitHub Copilot.

**Last Updated:** May 12, 2025

## Core Objective:
Develop a robust and viable ZenCtrl application, starting with the assimilation of the `LeniaOodaStrategy` for backtesting and visualization, augmented by ZEN's predictive (image generation) capabilities. The system should allow users to design strategies, visualize their playout in what-if scenarios, and progressively improve.

## Guiding Principles:

1.  **Iterative Development & Viability:**
    *   Focus on creating verifiably working and viable features in small, manageable increments.
    *   Prioritize functionality and stability at each step.
    *   Continuously seek to improve and refine existing features.

2.  **Progressive Living Documentation:**
    *   **`PLAN.md`**: Maintain a detailed, up-to-date plan for the current major feature integration (e.g., LeniaOodaStrategy assimilation). This document will be updated as tasks are completed or new insights emerge.
    *   **`COPILOT_WORKING_PRINCIPLES.md` (This file)**: Document our agreed-upon collaboration strategy and development guidelines.
    *   **`DEVELOPMENT_LOG.md` (To be created)**: Keep a log of significant development steps, key decisions made, summaries of complex prompt sequences, and outcomes of experiments. This will aid in reproducibility and understanding the project's evolution.
    *   **Code Comments & Docstrings**: Ensure new code is adequately commented, and public APIs/functions have clear docstrings.

3.  **Prompt Logging (Summarized):**
    *   While direct prompt export isn't feasible for Copilot, key interactions, complex instructions, and their outcomes will be summarized in `DEVELOPMENT_LOG.md` to ensure a traceable decision path.

4.  **Version Control (Git Workflow):**
    *   **Branching Strategy**: New features or significant refactoring will be done on dedicated branches (e.g., `draft/assimilate-lenia-ooda-strategy`).
    *   **Regular Commits**: Copilot will prompt the User to commit changes at logical checkpoints, especially after:
        *   A sub-task in `PLAN.md` is completed.
        *   The application builds successfully after modifications.
        *   Tests (if applicable and implemented) pass.
    *   Commit messages should be clear and descriptive.

5.  **Code Integrity & Best Practices:**
    *   **Preserve Working Code**: Do not delete or drastically alter code that is confirmed to be working without a clear reason (e.g., refactoring for improvement, replacement with a better alternative).
    *   **SOLID Principles**: Strive to apply SOLID principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion) when designing, generating, or refactoring code.
    *   **Modularity & Reusability**: Design components to be as modular and reusable as reasonably possible.

6.  **Testing (Future Consideration):**
    *   While not yet implemented, the plan should accommodate the future addition of unit and integration tests. Successful test runs will become a criterion for prompting commits.

7.  **Clear Communication:**
    *   Copilot will strive to explain its actions, the reasoning behind them, and the next steps.
    *   The User is encouraged to provide clear, specific instructions and feedback.

## Current Task Focus (from `PLAN.md`):
*   Assimilate `LeniaOodaStrategy.py` into ZenCtrl.
*   Integrate with Gradio UI for strategy design, simulation, and visualization.
*   Augment backtesting with ZEN's predictive image generation capabilities.

## Next Immediate Steps (as of May 12, 2025):
1.  Create `COPILOT_WORKING_PRINCIPLES.md` (this document).
2.  Create `DEVELOPMENT_LOG.md`.
3.  Install dependencies from `d:\source\ZenCtrl\requirements.txt`.
4.  Proceed with Phase 1, Step 4 (Configuration Management for `LeniaOodaStrategy.py`) as per `PLAN.md`.

This document will be considered "live" and can be updated by mutual agreement as the project evolves.
