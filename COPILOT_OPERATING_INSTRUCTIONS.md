# GitHub Copilot Operating Instructions

This document outlines the operating principles for GitHub Copilot in the ZenCtrl project. These instructions are designed to ensure development is iterative, verifiable, and leads to a viable, continuously improving product.

## Core Principles:

1.  **Verifiable Progress:**
    *   Prioritize creating features that can be demonstrably verified as working.
    *   Break down complex tasks into smaller, testable units.
    *   After implementing a feature or a significant change, suggest or perform verification steps (e.g., running the code, specific tests if available).

2.  **Iterative Development:**
    *   Follow the phased approach outlined in `PLAN.md`.
    *   Build upon existing, working code. Avoid large, monolithic changes.
    *   Embrace feedback and adjust plans as needed.

3.  **SOLID Principles:**
    *   Strive to apply SOLID (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion) principles in all code generation and refactoring tasks to promote maintainability, scalability, and robustness.

4.  **Code Integrity:**
    *   **Do Not Delete Working Code:** Preserve code that is functional unless explicitly agreed upon for refactoring or replacement with a verified, better alternative.
    *   **Refactor Carefully:** When refactoring, ensure changes are justified and improve the codebase (e.g., readability, performance, maintainability) without breaking existing functionality.

5.  **Living Documentation:**
    *   Actively maintain and update "living documents":
        *   `PLAN.md`: Reflect current project plans and progress.
        *   `COPILOT_WORKING_PRINCIPLES.md`: Adhere to the established collaboration guidelines.
        *   `DEVELOPMENT_LOG.md`: Keep a log of development activities, including summaries of user prompts, actions taken, and outcomes.
        *   This `COPILOT_OPERATING_INSTRUCTIONS.md` file itself.
    *   Ensure documentation accurately reflects the current state of the project and decisions made.

6.  **Version Control:**
    *   Prompt for or perform Git commits regularly, especially after:
        *   Successful implementation of a feature or sub-feature.
        *   Successful build and (if applicable) passing tests.
        *   Significant refactoring.
    *   Commit messages should be clear and descriptive.

7.  **Tool Usage & Context:**
    *   Utilize available tools effectively to gather context, search code, and perform actions.
    *   Always strive to understand the current project state and user intent before generating code or suggestions.
    *   If Azure-related tasks arise, use the `azure_development-get_best_practices` tool as per user instructions.

8.  **Continuous Improvement:**
    *   Be open to refining these operating instructions and other processes.
    *   Aim to make the ZenCtrl project increasingly viable and robust with each iteration.

## Prompt Logging:

Development activities, including a summary of user prompts, significant decisions, and actions taken by Copilot, will be logged in `DEVELOPMENT_LOG.md`. This log serves as a chronological record of the development process.

## Adherence:

I, GitHub Copilot, will strive to adhere to these operating instructions in all interactions and tasks related to the ZenCtrl project.
