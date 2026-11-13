import re
from pathlib import Path

import yaml

# Docs pages are plain Markdown, read both on GitHub and on the site. These checks keep links
# and Figures working in both places, so they follow the Markdown the pages use, nothing more.
CODE = re.compile(r"^```.*?^```|`[^`\n]*`", re.DOTALL | re.MULTILINE)
INLINE_LINK = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+)\)")
REFERENCE_LINK = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(\S+)", re.MULTILINE)


def front_matter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    return yaml.safe_load(text.split("---\n")[1]) or {}


def links(text: str) -> list[tuple[bool, str]]:
    """Each link outside code, as (is an image, target)."""
    prose = CODE.sub("", text)
    inline = [(image == "!", target) for image, target in INLINE_LINK.findall(prose)]
    return inline + [(False, target) for target in REFERENCE_LINK.findall(prose)]


def docs_problems(docs: Path) -> list[str]:
    """Everything wrong with the docs folder, one line per problem."""
    docs = docs.resolve()
    problems = []
    for page in sorted(docs.rglob("*.md")):
        name = page.relative_to(docs).as_posix()
        text = page.read_text()
        for field in ("title", "description"):
            if not front_matter(text).get(field):
                problems.append(f"{name}: has no {field} in its front matter")
        for image, target in links(text):
            if image:
                figure = (page.parent / target).resolve()
                if not (figure.is_file() and figure.parent == docs / "figures"):
                    problems.append(f"{name}: shows {target}, which isn't a Figure in figures/")
                continue
            path = target.split("#")[0]
            if not path or "://" in path:
                continue
            resolved = (page.parent / path).resolve()
            if not resolved.is_relative_to(docs):
                problems.append(f"{name}: links to {target}, which is outside the docs folder")
            elif not resolved.exists():
                problems.append(f"{name}: links to {target}, which doesn't exist")
    return problems


# A fenced block whose info string carries `title="<path>"` shows that file from Kettle.
TITLED_BLOCK = re.compile(
    r'^```\w*[^\n]*\btitle="([^"]+)"[^\n]*\n(.*?)^```', re.DOTALL | re.MULTILINE
)


def snippet_problems(docs: Path, kettle: Path) -> list[str]:
    """Each block titled with a file path that isn't that file in Kettle, word for word."""
    problems = []
    for page in sorted(docs.rglob("*.md")):
        name = page.relative_to(docs).as_posix()
        for path, shown in TITLED_BLOCK.findall(page.read_text()):
            file = kettle / path
            if not file.is_file():
                problems.append(
                    f"{name}: the block titled {path} is for a file Kettle doesn't have"
                )
            elif file.read_text() != shown:
                problems.append(
                    f"{name}: the block titled {path} doesn't match that file in Kettle"
                )
    return problems


DOCS = Path(__file__).parent.parent / "docs"


def test_the_docs_folder_has_the_shape_the_site_publishes():
    assert (DOCS / "index.md").is_file()
    for section in ("get-started", "concepts", "guides", "reference", "figures"):
        assert (DOCS / section).is_dir(), section
    assert (DOCS / "reference/json-output.md").is_file()


def test_the_docs_have_no_problems():
    assert docs_problems(DOCS) == []


def test_a_moved_page_redirects_from_where_it_was():
    page = front_matter((DOCS / "reference/json-output.md").read_text())

    assert page["redirects"] == ["json-output"]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


PAGE = "---\ntitle: A page\ndescription: What it says.\n---\n\n"


def test_a_broken_link_between_pages_is_a_problem(tmp_path: Path):
    write(tmp_path / "index.md", PAGE + "See [the JSON page](reference/jsn-output.md).\n")

    assert docs_problems(tmp_path) == [
        "index.md: links to reference/jsn-output.md, which doesn't exist"
    ]


def test_links_to_pages_sections_and_websites_are_fine(tmp_path: Path):
    write(tmp_path / "reference/json-output.md", PAGE + "Back to [the start](../index.md).\n")
    write(
        tmp_path / "index.md",
        PAGE
        + "See [rule IDs](reference/json-output.md#rule-ids), [below](#more)"
        + " and [the Way](https://nimblestax.com/way).\n\n## More\n",
    )

    assert docs_problems(tmp_path) == []


def test_a_broken_reference_style_link_is_a_problem(tmp_path: Path):
    write(tmp_path / "index.md", PAGE + "See [MSN201][msn201].\n\n[msn201]: reference/msn201.md\n")

    assert docs_problems(tmp_path) == [
        "index.md: links to reference/msn201.md, which doesn't exist"
    ]


def test_a_link_out_of_the_docs_folder_is_a_problem(tmp_path: Path):
    write(tmp_path.parent / "README.md", "# Mason\n")
    write(tmp_path / "index.md", PAGE + "See [the README](../README.md).\n")

    assert docs_problems(tmp_path) == [
        "index.md: links to ../README.md, which is outside the docs folder"
    ]


def test_links_shown_as_code_are_not_checked(tmp_path: Path):
    write(
        tmp_path / "index.md",
        PAGE + "Write `[MSN201](msn201.md)`, like this:\n\n```md\n![Figure](nope.svg)\n```\n",
    )

    assert docs_problems(tmp_path) == []


def test_every_page_has_a_title_and_a_description(tmp_path: Path):
    write(tmp_path / "index.md", "---\ntitle: Mason\n---\n\n# Mason\n")
    write(tmp_path / "guides/add-a-source.md", "# Add a Source\n")

    assert docs_problems(tmp_path) == [
        "guides/add-a-source.md: has no title in its front matter",
        "guides/add-a-source.md: has no description in its front matter",
        "index.md: has no description in its front matter",
    ]


def test_a_missing_figure_is_a_problem(tmp_path: Path):
    write(
        tmp_path / "concepts/deferral.md", PAGE + "![What a preview builds](../figures/dfr.svg)\n"
    )

    assert docs_problems(tmp_path) == [
        "concepts/deferral.md: shows ../figures/dfr.svg, which isn't a Figure in figures/"
    ]


def test_a_figure_lives_in_figures(tmp_path: Path):
    write(tmp_path / "figures/deferral.svg", "<svg/>")
    write(tmp_path / "concepts/stray.svg", "<svg/>")
    write(
        tmp_path / "concepts/deferral.md",
        PAGE + "![What a preview builds](../figures/deferral.svg)\n\n![Stray](stray.svg)\n",
    )

    assert docs_problems(tmp_path) == [
        "concepts/deferral.md: shows stray.svg, which isn't a Figure in figures/"
    ]


KETTLE = Path(__file__).parent.parent / "src/mason/examples/kettle"


def test_every_block_titled_with_a_file_path_matches_that_file_in_kettle():
    assert snippet_problems(DOCS, KETTLE) == []


def test_a_titled_block_that_differs_from_kettle_is_a_problem(tmp_path: Path):
    write(tmp_path / "kettle/domains/sales/seeds/regions.csv", "region_code,region_name\n")
    write(
        tmp_path / "docs/guides/add-a-seed.md",
        PAGE
        + '```csv title="domains/sales/seeds/regions.csv"\nregion_code,name\n```\n\n'
        + '```csv title="domains/sales/seeds/regions.csv"\nregion_code,region_name\n```\n',
    )

    assert snippet_problems(tmp_path / "docs", tmp_path / "kettle") == [
        "guides/add-a-seed.md: the block titled domains/sales/seeds/regions.csv"
        " doesn't match that file in Kettle"
    ]


def test_a_titled_block_for_a_file_kettle_lacks_is_a_problem(tmp_path: Path):
    (tmp_path / "kettle").mkdir()
    write(tmp_path / "docs/index.md", PAGE + '```yaml title="domains/tea.yaml"\nkind: seed\n```\n')

    assert snippet_problems(tmp_path / "docs", tmp_path / "kettle") == [
        "index.md: the block titled domains/tea.yaml is for a file Kettle doesn't have"
    ]
