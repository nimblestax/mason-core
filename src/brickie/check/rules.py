"""Project rules. `brickie validate` runs these with no workspace."""

from brickie import names, sql
from brickie.diagnostics import Diagnostic, error
from brickie.kinds.model import Model
from brickie.kinds.platform import SHARED_DOMAIN
from brickie.kinds.seed import Seed
from brickie.kinds.source import Source
from brickie.load.project import Project
from brickie.names import LogicalName


def check(project: Project) -> list[Diagnostic]:
    known = _tables(project)
    views = _materialized_views(project)
    diagnostics = []
    reads: dict[LogicalName, set[LogicalName]] = {}
    for model in project.models:
        file = model.sql_file.relative_to(project.root).as_posix()
        try:
            query = sql.parse(model.query)
        except sql.Unparseable as failure:
            diagnostics.append(_unparseable(file, failure))
            continue
        # A loop across Domains needs a read of another Domain's gold, which is its own failure.
        reads[_gold(project, model)] = {
            read for read in query.reads if read.domain == model.domain.lower()
        }
        diagnostics += _reads(project, known, file, query)
        diagnostics += _build_order(project, known, model, file, query)
        diagnostics += [
            _stream_of_materialized_view(file, query.streams[read])
            for read in sorted(query.streams.keys() & views, key=str)
        ]
        diagnostics += [_unqualified(file, name) for name in query.unqualified]
        diagnostics += [_computed(file, computed) for computed in query.computed]
        diagnostics += [_file_read(file, found) for found in query.file_reads]
        diagnostics += [_raw_placeholder(file, found) for found in query.raw_placeholders]
    return (
        diagnostics
        + _cycles(project, reads)
        + _seeds_named_like_sources(project)
        + _named_like_a_quarantine(project)
    )


def _reads(project: Project, known: set[LogicalName], file: str, query: sql.Query):
    """Every read must be a table in the project. A real table name gets its Logical Name."""
    diagnostics = []
    for read, written in sorted(query.reads.items(), key=lambda item: str(item[0])):
        if read in known:
            continue
        logical = names.logical_name_for(project, read)
        if logical in known:
            diagnostics.append(_real_name(file, written, logical))
        elif logical:
            diagnostics.append(_real_name_of_no_table(file, written, logical))
        else:
            diagnostics.append(_unresolved(file, written))
    return diagnostics


def _build_order(
    project: Project, known: set[LogicalName], model: Model, file: str, query: sql.Query
) -> list[Diagnostic]:
    """A Gold Model reads silver and gold, never bronze. Its own Domain's are all open to it, but
    from other Domains it reads only Exported silver and the Shared Domain's gold.

    So every read points to a step built earlier, and Domains can't read each other in a loop.
    """
    bronze, silver = (layer.lower() for layer in project.platform.source_layers)
    domain = model.domain.lower()
    published = _published(project, known, domain)
    upserts = {
        LogicalName(source.domain, silver, source.name)
        for source in project.sources
        if source.silver.keys
    }
    diagnostics = []
    for read, written in sorted(query.reads.items(), key=lambda item: str(item[0])):
        if read not in known:
            continue  # Reported as a table that isn't in the project.
        if read.layer == bronze:
            diagnostics.append(_bronze_read(file, written, read, silver))
        elif read.domain != domain and read not in published:
            if read.layer == silver:
                diagnostics.append(_private_silver(file, written, read))
            else:
                diagnostics.append(_other_domains_gold(file, written, read))
        elif read in query.streams and read in upserts:
            diagnostics.append(_stream_of_upsert(file, query.streams[read]))
    return diagnostics


def _published(project: Project, known: set[LogicalName], domain: str) -> set[LogicalName]:
    """What a Gold Model in `domain` may read from other Domains."""
    silver = project.platform.source_layers[1]
    tables = (*project.sources, *project.seeds)
    published = {
        LogicalName(table.domain, silver, table.name) for table in tables if _is_exported(table)
    }
    if domain != SHARED_DOMAIN:
        model_layers = {layer.lower() for layer in project.platform.model_layers}
        published |= {
            name for name in known if name.domain == SHARED_DOMAIN and name.layer in model_layers
        }
    return published


def _is_exported(table: Source | Seed) -> bool:
    return table.silver.export if isinstance(table, Source) else table.export


def _materialized_views(project: Project) -> set[LogicalName]:
    """Every table no stream may read: each Seed, and each Gold Model that reads no stream.

    A Gold Model whose SQL can't be read is left out, because it's reported on its own.
    """
    silver = project.platform.source_layers[1]
    views = {LogicalName(seed.domain, silver, seed.name) for seed in project.seeds}
    for model in project.models:
        try:
            streaming = sql.streams(model.query)
        except sql.Unparseable:
            continue
        if not streaming:
            views.add(_gold(project, model))
    return views


def _stream_of_materialized_view(file: str, written: sql.Found) -> Diagnostic:
    return error(
        "BRK212",
        file,
        f"{written.text} is a materialized view, which Databricks can recompute in full, and"
        " `STREAM(...)` reads only new rows. The pipeline would fail when it starts.",
        f"Read it without `STREAM(...)`, as `FROM {written.text}`, so this Gold Model refreshes"
        " from the whole table.",
        written.line,
    )


def _stream_of_upsert(file: str, written: sql.Found) -> Diagnostic:
    return error(
        "BRK211",
        file,
        f"{written.text} is upsert silver, which changes rows in place, and `STREAM(...)` reads"
        " only new rows. The pipeline would fail at runtime, after its first update.",
        f"Read it without `STREAM(...)`, as `FROM {written.text}`, so this Gold Model refreshes"
        " from the whole table.",
        written.line,
    )


def _bronze_read(file: str, written: sql.Found, read: LogicalName, silver: str) -> Diagnostic:
    return error(
        "BRK210",
        file,
        f"{written.text} is bronze, which only its silver reads. Bronze keeps rows as they"
        " landed, so a Gold Model reads silver, built after it.",
        f"Read {read.domain}.{silver}.{read.entity} instead.",
        written.line,
    )


def _private_silver(file: str, written: sql.Found, read: LogicalName) -> Diagnostic:
    return error(
        "BRK209",
        file,
        f"{written.text} is silver the {read.domain} Domain hasn't Exported,"
        " so only that Domain reads it.",
        f"Ask the {read.domain} Domain's owner to Export it, with `export: true` under a"
        " Source's `silver:` or in a Seed, or read a table it has Exported.",
        written.line,
    )


def _other_domains_gold(file: str, written: sql.Found, read: LogicalName) -> Diagnostic:
    return error(
        "BRK209",
        file,
        f"{written.text} is the {read.domain} Domain's gold. Nobody reads another Domain's gold,"
        " so each Domain can change its own.",
        f"Build it from silver the {read.domain} Domain has Exported, or move what's shared"
        " into the Shared Domain.",
        written.line,
    )


def _gold(project: Project, model: Model) -> LogicalName:
    return LogicalName(model.domain, model.layer, model.name)


def _cycles(project: Project, reads: dict[LogicalName, set[LogicalName]]) -> list[Diagnostic]:
    """Each loop of Gold Models reading each other, found once by a depth-first walk."""
    files = {
        _gold(project, model): model.sql_file.relative_to(project.root).as_posix()
        for model in project.models
    }
    finished: set[LogicalName] = set()
    diagnostics = []

    def walk(model: LogicalName, path: list[LogicalName]) -> None:
        path.append(model)
        for read in sorted(reads[model] & reads.keys(), key=_dotted):
            if read in path:
                cycle = path[path.index(read) :]
                first = cycle.index(min(cycle, key=_dotted))
                diagnostics.append(_cycle(files, cycle[first:] + cycle[:first]))
            elif read not in finished:
                walk(read, path)
        path.pop()
        finished.add(model)

    for model in sorted(reads, key=_dotted):
        if model not in finished:
            walk(model, [])
    return sorted(diagnostics, key=lambda diagnostic: diagnostic.file)


def _cycle(files: dict[LogicalName, str], cycle: list[LogicalName]) -> Diagnostic:
    loop = " → ".join(_dotted(model) for model in [*cycle, cycle[0]])
    return error(
        "BRK208",
        files[cycle[0]],
        "A Gold Model can't read itself, directly or through other Gold Models,"
        f" because each must be built before it's read: {loop}.",
        "Remove one of these reads, so each Gold Model reads only tables built before it.",
    )


def _tables(project: Project) -> set[LogicalName]:
    tables = set()
    for source in project.sources:
        for layer in project.platform.source_layers:
            tables.add(LogicalName(source.domain, layer, source.name))
        if source.silver.quarantining:
            silver = project.platform.source_layers[1]
            tables.add(LogicalName(source.domain, silver, source.quarantine))
    for seed in project.seeds:
        tables.add(LogicalName(seed.domain, project.platform.source_layers[1], seed.name))
    for model in project.models:
        tables.add(_gold(project, model))
    return tables


def _seeds_named_like_sources(project: Project) -> list[Diagnostic]:
    silver = project.platform.source_layers[1]
    sources = {(source.domain, source.name) for source in project.sources}
    return [
        error(
            "BRK202",
            seed.config_file.relative_to(project.root).as_posix(),
            f"{seed.domain}.{silver}.{seed.name} is both a Seed and a Source.",
            "Rename the Seed or the Source, so each has its own table.",
        )
        for seed in project.seeds
        if (seed.domain, seed.name) in sources
    ]


def _named_like_a_quarantine(project: Project) -> list[Diagnostic]:
    """A Source's Quarantine table is in silver's schema, so no other table may take its name."""
    silver = project.platform.source_layers[1]
    quarantines = {
        (source.domain, source.quarantine): source.name
        for source in project.sources
        if source.silver.quarantining
    }
    return [
        error(
            "BRK202",
            table.config_file.relative_to(project.root).as_posix(),
            f"{table.domain}.{silver}.{table.name} is also the Quarantine table"
            f" of the Source {quarantines[(table.domain, table.name)]}.",
            "Rename this file, so each table has its own name.",
        )
        for table in (*project.sources, *project.seeds)
        if (table.domain, table.name) in quarantines
    ]


def _unresolved(file: str, read: sql.Found) -> Diagnostic:
    return error(
        "BRK201",
        file,
        f"{read.text} isn't a table in this project.",
        "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
        read.line,
    )


def _real_name(file: str, real: sql.Found, logical: LogicalName) -> Diagnostic:
    return error(
        "BRK205",
        file,
        f"{real.text} is a real table name, which names one Environment.",
        f"Use its Logical Name, {_dotted(logical)}, so the same SQL works in every Environment.",
        real.line,
    )


def _real_name_of_no_table(file: str, real: sql.Found, logical: LogicalName) -> Diagnostic:
    return error(
        "BRK205",
        file,
        f"{real.text} is a real table name, and no table called {_dotted(logical)}"
        " is in this project.",
        f"Declare a Source, Seed or Gold Model called {_dotted(logical)}, or correct the name.",
        real.line,
    )


def _file_read(file: str, found: sql.Found) -> Diagnostic:
    return error(
        "BRK206",
        file,
        f"{found.text} reads data that isn't a table in this project,"
        " so Brickie can't check it or point it at each Environment.",
        "A Gold Model reads tables. Declare a Source for these files"
        " and read its silver table by Logical Name.",
        found.line,
    )


def _raw_placeholder(file: str, found: sql.Found) -> Diagnostic:
    return error(
        "BRK207",
        file,
        f"{found.text} holds `${{`, so the pipeline could replace it with a setting's value,"
        " and a raw string can't hold the escape that stops it.",
        "Write it as an ordinary string, doubling each backslash, and Brickie escapes the `${`.",
        found.line,
    )


def _dotted(name: LogicalName) -> str:
    return f"{name.domain}.{name.layer}.{name.entity}"


def _unqualified(file: str, name: sql.Found) -> Diagnostic:
    return error(
        "BRK201",
        file,
        f"`{name.text}` isn't a CTE or a Logical Name, so Brickie can't tell which table it reads.",
        "Write the table as a three-part Logical Name, such as sales.silver.orders,"
        " or define a CTE with this name.",
        name.line,
    )


def _unparseable(file: str, failure: sql.Unparseable) -> Diagnostic:
    return error(
        "BRK203",
        file,
        f"Brickie can't read this SQL, so it can't tell what it reads. {failure.reason}",
        "Make the file one Databricks SQL query that runs on its own.",
        failure.line,
    )


def _computed(file: str, computed: sql.Found) -> Diagnostic:
    return error(
        "BRK204",
        file,
        f"{computed.text} builds a table name as the query runs,"
        " so Brickie can't see what it reads.",
        "Write the table as a Logical Name, such as sales.silver.orders,"
        " so every read shows in review.",
        computed.line,
    )
