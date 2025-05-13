# GitHub Copilot Operating Instructions

This document outlines the operating principles for GitHub Copilot in the ZenCtrl project. These instructions are designed to ensure development is iterative, verifiable, and leads to a viable, continuously improving product.

## Core Principles:

1.  **Strategic Objective: Windfall through Gamified Strategy Execution:**
    *   The ultimate aim is to achieve a significant "windfall" by discovering, developing, and deploying novel strategies.
    *   These strategies will be conceptualized through the lens of game theory, where the system and its components ("agents") are actors performing on a metaphorical "octagon stage."
    *   Development will focus on creating a gamified environment where strategies evolve to overcome "unnecessary obstacles" and "boss levels," representing market challenges or inefficiencies.
    *   Copilot's suggestions and implementations should align with this narrative, fostering the creation of adaptive, intelligent agents and systems that can identify and capitalize on such strategic opportunities.

2.  **Verifiable Progress:**
    *   Prioritize creating features that can be demonstrably verified as working towards the strategic objective.
    *   Break down complex tasks into smaller, testable units that contribute to the gamified strategy framework.
    *   After implementing a feature or a significant change, suggest or perform verification steps (e.g., running the code, specific tests if available, simulations within the gamified context).

3.  **Iterative Development:**
    *   Follow the phased approach outlined in `PLAN.md`, adapting it to serve the strategic objective.
    *   Build upon existing, working code, iteratively enhancing the "game" and the "actors."
    *   Embrace feedback and adjust plans as needed to better pursue windfall opportunities.

4.  **SOLID Principles:**
    *   Strive to apply SOLID (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion) principles in all code generation and refactoring tasks to promote maintainability, scalability, and robustness of the "game engine" and "agent" architecture.

5.  **Code Integrity:**
    *   **Do Not Delete Working Code:** Preserve code that is functional unless explicitly agreed upon for refactoring or replacement with a verified, better alternative that aligns more closely with the strategic objective.
    *   **Refactor Carefully:** When refactoring, ensure changes are justified and improve the codebase (e.g., readability, performance, maintainability) without breaking existing functionality, always keeping the "windfall via gamification" goal in mind.

6.  **Living Documentation:**
    *   Actively maintain and update "living documents":
        *   `PLAN.md`: Reflect current project plans and progress, framed by the strategic objective.
        *   `COPILOT_WORKING_PRINCIPLES.md`: Adhere to the established collaboration guidelines.
        *   `DEVELOPMENT_LOG.md`: Keep a log of development activities, including summaries of user prompts, actions taken, and outcomes, particularly how they relate to the gamified strategy.
        *   This `COPILOT_OPERATING_INSTRUCTIONS.md` file itself.
    *   Ensure documentation accurately reflects the current state of the project and decisions made in pursuit of the strategic objective.

7.  **Version Control:**
    *   Prompt for or perform Git commits regularly, especially after:
        *   Successful implementation of a feature or sub-feature contributing to the "game."
        *   Successful build and (if applicable) passing tests.
        *   Significant refactoring.
    *   Commit messages should be clear and descriptive, ideally referencing the strategic objective where relevant.

8.  **Tool Usage & Context:**
    *   Utilize available tools effectively to gather context, search code, and perform actions in service of the strategic objective.
    *   Always strive to understand the current project state and user intent before generating code or suggestions.
    *   If Azure-related tasks arise, use the `azure_development-get_best_practices` tool as per user instructions.

9.  **Continuous Improvement:**
    *   Be open to refining these operating instructions and other processes to better achieve the strategic objective.
    *   Aim to make the ZenCtrl project increasingly viable and robust with each iteration, moving closer to the "windfall."

## Prompt Logging:

Development activities, including a summary of user prompts, significant decisions, and actions taken by Copilot, will be logged in `DEVELOPMENT_LOG.md`. This log serves as a chronological record of the development process.

## Adherence:

I, GitHub Copilot, will strive to adhere to these operating instructions in all interactions and tasks related to the ZenCtrl project.
