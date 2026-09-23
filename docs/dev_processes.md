# JobRec Development Process

## Branching/Workflow Model

Our team uses a model inspired by **GitHub Flow**. This model has two overall branch types: a single main branch and individual feature branches for development work.

### Main Branches

| Branch    | Purpose                                                                 |
|-----------|--------------------------------------------------------------------------|
| `main`    | Always working, and deployable. This branch is the current working version of JobRec all of the time. The main branch is only updated via reviewed Pull Requests. It should never be committed to directly. |
| `feature/*` | These are temporary branches where individual team members code and add their specific tasks, such as features, bug fixes, tests, and docs, in isolation before submitting a pull request, and eventually merging these features onto `main`. |


Examples:
- `feature/1-resume-upload`
- `feature/10-test-resumes`
- `feature/44-auth-flow`

Each feature branch is associated with one GitHub Issue. The issue number in the branch name keeps names short and guaranteed-unique (as GitHub issue numbers never repeat), and lets anybody be able to trace the branch back to the issue, using only 1 click.

**Requirement Traceability** Linking work to our Software Development Plan is handled at the **Issue** and **PR** level rather than in the branch name itself. Specifically, when an issue maps to a functional requirement defined, its description references the FR ID (Such as "Implement FR-003: Accurate Job Data Scraping"). This leads to avoiding the cramming of multiple identifiers into branch names, as a single requirement (like FR-001) can be relevant to multiple issues and branches over time, and many issues (such as bug fixes, refactors, config changes) can sometimes not even map to a single requirement.

**Feature Branches are Temporary.** They exist only for the duration of the task they were created for. Once a feature branch's PR has been reviewed, approved, and merged into `main`, the branch **has to be deleted**. This rule is enforced automatically via GitHub's "Automatically delete head branches" setting (Settings → General → Pull Requests), and should also be verified by the branch owner if deleted manually. This keeps the repository's branch list clean and navigatable, and prevents too many unused branches on the GitHub page.

### Workflow

1. A GitHub Issue is created for the task. If the task maps to a specific requirement, the issue description contains the reference to the FR or NFR ID (e.g., FR-001, NFR-003). The GitHub Issue also contains a deadline, as well as the team member(s) assigned to the task.
2. When working on the issue, the team member tasked creates a `feature/` branch off the latest `main`, named per the convention above.
3. Work is developed and committed on that feature branch.
4. `main` is kept up to date locally by periodically pulling, so that feature branches code is not too far off from the main branch code before merging.
5. When the feature is complete and tested, a Pull Request is opened that targets the `main` branch.
6. After the PR is reviewed, approved, and merged by another team member, `main` stays deployable and the feature branch is deleted automatically/manually. 
7. Workflow repeats again.

### Handling Larger Features

For work that encompasses multiple smaller tasks, such as building an entire feature like the job recommendation algorithm for JobRec, we use a **parent issue + child issues** pattern:

- A parent Issue is created describing the overall feature and referencing the relevant requirement ID (Such as FR-003).
- Child Issues are created for each concrete unit of work under that feature, referencing the parent issue (Such as "Part of #1").
- Each Child Issue gets its own `feature/<issue-number>-<description>` branch and PR, so that individual PRs are small and reviewable.
- Finally, the Parent Issue is closed once all Child Issues are completed and merged.

This ensures that large, hard-to-review PRs are avoided, and also keeps big-picture feature tracking all in one place.

---

## Pull Request Process

### PR Naming Convention

Example: `[#3] Add resume upload endpoint (FR-003)`

The '[#3]' is an example for the GitHub Issue number that the feature resolves. Furthermore, where relevant, the associated requirement ID (FR-XXX / NFR-XXX) is included in the title or description for traceability back to our Software Development Plan. 

### Linking Issues to PRs

Every PR description contains a GitHub closing keyword (Such as `Closes`, `Fixes`, or `Resolves`) alongside the GitHub Issue Number. This links the PR to its issue in the GitHub UI and automatically closes the issue when the PR merges into `main`.

**Example:**

> **PR Title:** `[#3] Add resume upload endpoint (FR-003)`
>
> **PR Description:**
> ```
> Closes #3
>
> Implements the resume upload endpoint described in FR-003 
> (Accurate Job Data Scraping). With this feature, the platform
> accepts PDF uploads, extracts text, and stores it for downstream 
> skill extraction. Feature has been verified manually against sample resumes.
> ```

### Code Review Policy

- Every PR requires **at least 1 approval** from a teammate other than the author before merging.
- Self-merging onto `main` is **not allowed**.
- Pull Request reviewers must check for:
  - Correctness and passing tests
  - Adherence to code style and convention
  - Comments explaining at least the general purposes of code blocks
  - Whether the PR satisfies its linked issue and requirement (e.g., a PR closing an FR-003 issue is checked using FR-003's stated Test Method defined from the Initial Software Development Plan Document)
  - Security/privacy considerations for any PR touching user PII, authentication, or resume/skills data, per NFR-003 (User Data Protection)
  - Accessibility considerations for any PR touching UI, per NFR-002 and our commitment WCAG 2.2 guidelines
- Reviewers leave inline comments, and the author pushes follow-up commits to the same feature branch to fix additional issues or update code based on feedback.

### Merging Policy

- **`feature/*` → `main`:** Requires 1 approval from a team member and a passing build/tests before merge. Pull requests should be merged using **squash merge** to keep history clean and `main` deployable at all times.
- Larger or riskier changes (Such as authentication flows) necessitate review from at least one teammate familiar with that part of the system before merging.
- The feature branch is deleted immediately after merge.

## Two-Week Development Cycle

### Closing a Two-Week Cycle

At the end of each two-week development cycle, our regular team meeting (separate from the one with our professor) will be dedicated to verification of the previous two-week cycle before continuing with the next two weeks. Each team member will verify the integrity of their development by demonstrating proper tests were written in accordance with their development when necessary.

After verification of the previous two weeks, each team member will then verify the status of their assigned issues. Team members will ensure that the issues currently assigned to them are not complete yet and will be completed in a timely manner in the next two-week development cycle.

The team will also review progress before beginning the next cycle; if a team member needs work reassigned due to outside time constraints, that will be discussed in this meeting. 

This meeting will also be dedicated to refreshing the project views as outlined in the next section.

### Refreshing GitHub Project Views

After completion of a two week development cycle, the GitHub project views will be updated to reflect what was discussed in the development closure meeting. Issues resolved will be placed into "Done", if not done so already. Issues awaiting merge approval will be placed into "In Review", if not done so already. Issues planning to be worked on within the next two weeks will be placed into "In Progress" in the GitHub views. 

Any issues that seem to have been more complicated than anticipated will be moved into the "Backlog", permitting they are not a high priority dependency.

## Repository Architechture

The JobRec repository is organized such that all different areas of the project have its own dedicated folder. For example, all source code is within the src directory, while all relevant test files are under the src directory. Other directories are dedicated to documentation and storage of different helpers and executable files.

### Repository Structure

```text
app
│
├── deploy
│
├── helpers
│   └── example.sh
│
├── src
│   ├── templates
│   └── uploads
│
└── test
    └── test_resumes

docs
```

### Directory Descriptions

- `app/` – Contains the main application-related files and directories.

- `app/deploy/` – Stores deployment-ready executables and other files needed for deployment.

- `app/helpers/` – Contains helper scripts and utility functions used by the application.

- `app/src/` – Contains the main source code for the application.

- `app/src/templates/` – Stores HTML templates used by the web application.

- `app/src/uploads/` – Local directory used to store uploaded files during development and testing.

- `app/test/` – Contains files used for testing the application.

- `app/test/test_resumes/` – Stores dummy or sample resumes used when testing resume-processing functionality.

- `docs/` – Contains project documentation, including development-process documentation.