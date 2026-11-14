"""Loads a Project from disk: finds each Kind's files and has the Kind check what's beside them."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brickie.diagnostics import Diagnostic, error
from brickie.kinds import IN_DOMAINS, model, platform
from brickie.kinds.base import IDENTIFIER, InDomain, config_files
from brickie.kinds.model import Model
from brickie.kinds.platform import Platform
from brickie.kinds.seed import Seed
from brickie.kinds.source import Source
from brickie.load import config


@dataclass(frozen=True)
class Project:
    root: Path
    platform: Platform
    sources: tuple[Source, ...]
    seeds: tuple[Seed, ...]
    models: tuple[Model, ...]


def load(root: Path) -> Project:
    contract = config.load(root, root / platform.FILE_NAME, platform.KIND, Platform)
    found: dict[str, list[Any]] = {kind.KIND: [] for kind in IN_DOMAINS}
    problems = _unlisted_domain_folders(root, contract.domains)
    for domain in contract.domains:
        for kind in IN_DOMAINS:
            kind_folder = root / "domains" / domain / kind.FOLDER
            in_domain: list[Any] = []
            for folder in _tree(kind_folder):
                if kind is model and not _in_a_model_layer(kind_folder, folder, contract):
                    problems += [
                        _outside_a_layer(root, file, contract) for file in _model_files(folder)
                    ]
                    continue
                documents, found_problems = _read_folder(root, kind_folder, folder, kind)
                problems += found_problems
                in_domain += documents
            problems += _one_table_each(root, in_domain)
            found[kind.KIND] += in_domain
    if problems:
        raise config.InvalidConfig(problems)
    return Project(
        root,
        contract,
        tuple(found["source"]),
        tuple(found["seed"]),
        tuple(found["model"]),
    )


def _tree(kind_folder: Path) -> list[Path]:
    """A Kind's folder and every folder under it, at any depth. Only a Gold Model's first folder
    carries meaning, so the rest only group files."""
    if not kind_folder.is_dir():
        return []
    below = (path for path in kind_folder.rglob("*") if path.is_dir())
    visible = [path for path in below if not _hidden(path.relative_to(kind_folder))]
    return [kind_folder, *sorted(visible)]


def _hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)


def _in_a_model_layer(kind_folder: Path, folder: Path, contract: Platform) -> bool:
    """A Gold Model's Layer is the first folder under `models/`, so it must be a model Layer."""
    parts = folder.relative_to(kind_folder).parts
    return bool(parts) and parts[0] in contract.model_layers


def _model_files(folder: Path) -> list[Path]:
    """Each Gold Model's config file, and each SQL file with none beside it."""
    configs = config_files(folder)
    stems = {file.stem for file in configs}
    lone_sql = [file for file in sorted(folder.glob("*.sql")) if file.stem not in stems]
    return [*configs, *lone_sql]


def _outside_a_layer(root: Path, file: Path, contract: Platform) -> Diagnostic:
    layers = ", ".join(contract.model_layers)
    return error(
        "BRK127",
        file.relative_to(root).as_posix(),
        "This file isn't in a model Layer's folder, and a Gold Model's Layer is the first folder"
        " under `models/`.",
        f"Move it into a folder named after a model Layer: {layers}. To add a Layer, add it to"
        f" `naming.layers.models` in {platform.FILE_NAME}.",
    )


def _read_folder(
    root: Path, kind_folder: Path, folder: Path, kind: Any
) -> tuple[list[Any], list[Diagnostic]]:
    """One folder's documents, `Any` because each Kind loads its own model, and its problems."""
    files, problems = _one_per_name(root, config_files(folder))
    documents: list[Any] = []
    for file in files:
        if not re.fullmatch(IDENTIFIER, file.stem):
            problems.append(_invalid_name(root, file))
            continue
        result = config.read(root, file, kind.KIND)
        if isinstance(result, list):
            problems += result
        elif isinstance(result, InDomain):
            documents.append(result.at(file, kind_folder))
    problems += kind.problems(root, folder, documents)
    return documents, problems


def _invalid_name(root: Path, file: Path) -> Diagnostic:
    """A table's name comes from its config file's name, and SQL takes it unquoted."""
    suggested = re.sub(r"[^A-Za-z0-9_]", "_", file.stem)
    if suggested[0].isdigit():
        suggested = f"_{suggested}"
    return error(
        "BRK117",
        file.relative_to(root).as_posix(),
        f"`{file.stem}` isn't a valid table name. It may hold only letters, digits and"
        " underscores, and may not start with a digit.",
        f"Rename the file to `{suggested}.yaml`.",
    )


def _one_per_name(root: Path, files: list[Path]) -> tuple[list[Path], list[Diagnostic]]:
    """A name's one config file. Both `orders.yaml` and `orders.yml` would be two tables."""
    by_name: dict[str, list[Path]] = {}
    for file in files:
        by_name.setdefault(file.stem, []).append(file)
    single = [found[0] for found in by_name.values() if len(found) == 1]
    both = [_duplicate(root, found) for found in by_name.values() if len(found) > 1]
    return single, both


def _one_table_each(root: Path, documents: list[InDomain]) -> list[Diagnostic]:
    """Folders below a Layer carry no meaning, so one name in one Domain's Layer is one table."""
    by_table: dict[tuple[str, str], list[Path]] = {}
    for document in documents:
        layer = document.layer if isinstance(document, Model) else ""
        # Databricks ignores case in table names, so `Orders` and `orders` are one table.
        by_table.setdefault((layer, document.name.lower()), []).append(document.config_file)
    return [_same_table(root, files) for files in by_table.values() if len(files) > 1]


def _same_table(root: Path, files: list[Path]) -> Diagnostic:
    first, *rest = (file.relative_to(root).as_posix() for file in files)
    return error(
        "BRK120",
        rest[-1],
        f"{first} and {', '.join(rest)} both configure {files[0].stem} in one Domain's Layer,"
        " and folders inside a Layer only group files, so Brickie can't tell which one is meant.",
        "Rename one of them, so each table has its own name, or delete one.",
    )


def _duplicate(root: Path, files: list[Path]) -> Diagnostic:
    first, *rest = sorted(files, key=lambda file: file.suffix != ".yaml")
    return error(
        "BRK120",
        rest[-1].relative_to(root).as_posix(),
        f"{first.name} and {', '.join(file.name for file in rest)} both configure"
        f" {first.stem}, so Brickie can't tell which one is meant.",
        "Keep one of them, and delete or rename the other.",
    )


def _unlisted_domain_folders(root: Path, domains: list[str]) -> list[Diagnostic]:
    """A folder under `domains/` is a Domain only if `domains` names it, in the same case."""
    folders = root / "domains"
    if not folders.is_dir():
        return []
    return [
        _unlisted(folder.name, domains)
        for folder in sorted(folders.iterdir())
        if folder.is_dir() and not folder.name.startswith(".") and folder.name not in domains
    ]


def _unlisted(folder: str, domains: list[str]) -> Diagnostic:
    file = f"domains/{folder}"
    same_but_case = [domain for domain in domains if domain.lower() == folder.lower()]
    if same_but_case:
        return error(
            "BRK121",
            file,
            f"`domains` in {platform.FILE_NAME} lists {same_but_case[0]}, not {folder}."
            " Only a file system that ignores case reads this folder for it.",
            f"Change {same_but_case[0]} to {folder} in `domains` in {platform.FILE_NAME},"
            " so it matches the folder's case.",
        )
    return error(
        "BRK121",
        file,
        f"`domains` in {platform.FILE_NAME} doesn't list {folder},"
        " so nothing in this folder is validated or deployed.",
        f"Add {folder} to `domains` in {platform.FILE_NAME}, matching the folder's case,"
        " or remove the folder.",
    )
