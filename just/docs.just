# Write the generated reference pages into docs/. Commit what changes.
generate:
    uv run python -m brickie.reference {{justfile_directory()}}/docs
