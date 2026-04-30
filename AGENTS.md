# Agent Guidelines

## Language

All content in this file and in any spec file must be written in **English only**.

## Specification Files

- All spec files must be created exclusively in the `docs/specs/` directory.
- No spec files should be created in any other directory (e.g., `docs/superpowers/specs/` or any nested path outside `docs/specs/`).
- Spec filenames must follow the format: `YYYY-MM-DD-<topic>-design.md`.

## Git Commits

- All commit messages must be written in **English only**.
- All commits must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification.
- Format: `<type>(<optional scope>): <description>`
- Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`.
- Examples:
  - `feat(mcp): add search_food tool`
  - `fix(db): correct calorie calculation for partial quantities`
  - `docs: update setup instructions in README`
  - `chore: add CLAUDE.md symlink`
