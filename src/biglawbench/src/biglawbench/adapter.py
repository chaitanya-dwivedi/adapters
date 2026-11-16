"""Adapter: BigLaw Bench Core (public sample, 6 tasks) -> Harbor tasks.

Source: https://github.com/harveyai/biglaw-bench (pinned commit). PDFs are downloaded at
generation time; nothing from the upstream dataset is committed to this repo.
"""

import csv
import io
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

UPSTREAM = "harveyai/biglaw-bench"
COMMIT = "138fd481b459a00bbd98eeb710f69ada1052bd47"
RAW = f"https://raw.githubusercontent.com/{UPSTREAM}/{COMMIT}/blb-core"
TEMPLATE_DIR = Path(__file__).parent / "task-template"

_VERBS = {"state", "mention", "provide", "identify", "explain", "recommend", "note", "discuss",
          "include", "address", "acknowledge", "propose", "analyze", "highlight", "describe",
          "establish", "reference", "suggest", "conclude", "cite", "recognize", "outline", "say"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _fetch(path: str) -> bytes:
    url = f"{RAW}/{urllib.parse.quote(path)}"
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def criterion_to_statement(q: str) -> str:
    """Turn a rubric question ('Does the response state that X?') into a declarative statement."""
    q = re.sub(r"\s*\((\d+(?:\.\d+)?)\s*points?\)\s*$", "", q.strip()).rstrip("?").strip()
    m = re.match(r"^Does (the [\w'\- ]+?) (\w+)\b(.*)$", q)
    if m and m.group(2).lower() in _VERBS:
        verb = m.group(2)
        verb = verb + ("es" if verb.endswith(("s", "sh", "ch")) else "s")
        return f"{m.group(1).capitalize()} {verb}{m.group(3)}."
    m = re.match(r"^Do (the [\w'\- ]+?) (\w+)\b(.*)$", q)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}{m.group(3)}."
    m = re.match(r"^(Is|Are) (the [\w'\- ]+?) ((?:in|written|a|an|formatted|structured|organized)\b.*)$", q)
    if m:
        return f"{m.group(2).capitalize()} {m.group(1).lower()} {m.group(3)}."
    return f"The response satisfies the following requirement: {q}."


def reference_answer(rubric: str, prompt: str) -> str:
    """Rubric-derived reference answer: every affirmative criterion restated as a satisfied statement."""
    out = [f"# Reference response\n\nTask: {prompt}\n"]
    section = ""
    for line in rubric.splitlines():
        s = line.strip()
        if re.match(r"^negative points", s, re.I):
            break
        m = re.search(r"\((\d+(?:\.\d+)?)\s*points?\)\s*$", s)
        if m:
            body = re.sub(r"^[a-zA-Z0-9]+\.?\s+(?=[A-Z])", "", s)
            out.append(f"- {criterion_to_statement(body)}")
        elif s and not s.lower().startswith("affirmative"):
            label = re.sub(r"^\d+\.\s*", "", s).rstrip(":")
            if label != section and not re.match(r"^[a-z]\.\s", s):
                out.append(f"\n## {label}\n")
                section = label
    return "\n".join(out) + "\n"


class BigLawBenchAdapter:
    def __init__(self, output_dir: Path, limit: int | None = None, overwrite: bool = False,
                 task_ids: list[str] | None = None, **kwargs):
        self.output_dir = Path(output_dir)
        self.limit = limit
        self.overwrite = overwrite
        self.task_ids = task_ids

    def load_records(self) -> list[dict]:
        text = _fetch("core-samples.csv").decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))

    @staticmethod
    def task_id(rec: dict) -> str:
        return f"blb-core-{int(rec['Number']):03d}"

    def run(self) -> None:
        records = self.load_records()
        if self.task_ids:
            wanted = {t.lower() for t in self.task_ids}
            records = [r for r in records if self.task_id(r) in wanted or str(int(r["Number"])) in wanted]
        if self.limit is not None:
            records = records[: self.limit]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for rec in records:
            self._generate(rec)

    def _generate(self, rec: dict) -> None:
        tid = self.task_id(rec)
        dest = self.output_dir / tid
        if dest.exists():
            if not self.overwrite:
                print(f"skip {tid} (exists; use --overwrite)")
                return
            shutil.rmtree(dest)
        shutil.copytree(TEMPLATE_DIR, dest)
        docs = [d.strip() for d in rec["Document(s)"].splitlines() if d.strip() and d.strip().upper() != "N/A"]
        (dest / "environment" / "documents").mkdir(parents=True)
        (dest / "environment" / "documents" / ".keep").write_text("")
        for d in docs:
            (dest / "environment" / "documents" / d).write_bytes(_fetch(f"documents/{d}"))

        prompt = rec["Prompt"].strip()
        rubric = rec["Rubric"].strip() + "\n"
        subs = {
            "{task_id}": tid, "{number}": str(int(rec["Number"])),
            "{task_summary}": rec["Task"].strip().replace('"', "'"),
            "{category_kw}": _slug(rec["Category"]), "{task_type_kw}": _slug(rec["Task Type"]),
            "{category}": rec["Category"].strip(), "{task_type}": rec["Task Type"].strip(),
        }
        toml = (dest / "task.toml").read_text()
        for k, v in subs.items():
            toml = toml.replace(k, v)
        (dest / "task.toml").write_text(toml)
        instr = (dest / "instruction.md").read_text()
        if docs:
            doc_block = ("The attached documents are available in `/app/documents/` (PDF files; `pdftotext` is installed):\n\n"
                         + "\n".join(f"- `/app/documents/{d}`" for d in docs) + "\n\n")
        else:
            doc_block = "No documents are attached; everything needed is in the request above.\n\n"
        instr = instr.replace("{prompt}", prompt).replace("{doc_block}", doc_block)
        (dest / "instruction.md").write_text(instr)
        (dest / "tests" / "rubric.md").write_text(rubric)
        (dest / "solution" / "answer.md").write_text(reference_answer(rubric, prompt))
        (dest / "solution" / "solve.sh").chmod(0o755)
        (dest / "tests" / "test.sh").chmod(0o755)
        print(f"generated {tid} ({len(docs)} docs)")
