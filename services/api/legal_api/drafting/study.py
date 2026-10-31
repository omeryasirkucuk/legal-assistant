"""Learn drafting practice from petition samples published on the web.

Lawyers and law firms publish sample petitions to be used. This reads the pages listed in
playbooks/tr/petitions/sources.json (robots.txt respected, one request per second per host),
keeps their text in var/petition_samples (not in the repository), and has the cheap model
note for each sample its structure, formulas, requests, evidence and common points. The notes
of all samples of a type are then merged into that type's practice notes
(playbooks/tr/petitions/<type>.practice.md), written in our own words.

    uv run python -m legal_api.drafting.study fetch
    uv run python -m legal_api.drafting.study learn
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from legal_api import llm
from legal_api.config import REPO_ROOT
from legal_api.drafting.types import PETITIONS_DIR
from legal_api.files.extract import UnsupportedFile, text_of
from legal_api.prompts import prompt
from legal_api.sources.gateway import USER_AGENT

SOURCES = PETITIONS_DIR / "sources.json"
CACHE = REPO_ROOT / "var" / "petition_samples"
MIN_CHARS = 800
MAX_SAMPLE_CHARS = 20000
_SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "td", "br", "div", "blockquote"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _path(type_id: str, url: str):
    return CACHE / type_id / f"{hashlib.sha1(url.encode()).hexdigest()[:12]}.txt"


async def fetch() -> None:
    robots: dict[str, urllib.robotparser.RobotFileParser] = {}
    last: dict[str, float] = {}
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30,
                                 follow_redirects=True) as client:
        for type_id, urls in json.loads(SOURCES.read_text(encoding="utf-8")).items():
            for url in urls:
                out = _path(type_id, url)
                if out.exists():
                    continue
                host = urlparse(url).netloc
                if host not in robots:
                    rp = urllib.robotparser.RobotFileParser(f"https://{host}/robots.txt")
                    try:
                        r = await client.get(f"https://{host}/robots.txt")
                        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                    except httpx.HTTPError:
                        rp.parse([])
                    robots[host] = rp
                if not robots[host].can_fetch(USER_AGENT, url):
                    print(f"robots.txt disallows {url}")
                    continue
                await asyncio.sleep(max(0.0, 1.0 - (time.monotonic() - last.get(host, 0))))
                last[host] = time.monotonic()
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except httpx.HTTPError as e:
                    print(f"failed {url}: {e}")
                    continue
                name = urlparse(str(r.url)).path
                try:
                    text = (text_of(name, r.content) if name.lower().endswith((".pdf", ".docx"))
                            else html_text(r.text))
                except UnsupportedFile:
                    continue
                if len(text) < MIN_CHARS:
                    print(f"too short {url}")
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(f"{url}\n\n{text}", encoding="utf-8")
                print(f"saved {type_id} {len(text)} chars {url}")


async def _ask(system: str, content: str, usage: llm.Usage, purpose: str) -> str:
    response = await llm.create("cheap", usage, purpose, max_tokens=6000, system=system,
                                messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in response.content if b.type == "text").strip()


async def learn() -> None:
    usage = llm.Usage()
    for type_dir in sorted(p for p in CACHE.iterdir() if p.is_dir()):
        type_id = type_dir.name
        samples = [p.read_text(encoding="utf-8") for p in sorted(type_dir.glob("*.txt"))]
        notes = await asyncio.gather(*(
            _ask(prompt("study_sample"), s[:MAX_SAMPLE_CHARS], usage, "study_sample")
            for s in samples))
        merged = await _ask(prompt("study_merge"), "\n\n=====\n\n".join(notes), usage,
                            "study_merge")
        (PETITIONS_DIR / f"{type_id}.practice.md").write_text(merged + "\n", encoding="utf-8")
        print(f"{type_id}: {len(samples)} samples, ${usage.cost_usd:.3f} so far")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["fetch", "learn"])
    step = parser.parse_args().step
    asyncio.run(fetch() if step == "fetch" else learn())


if __name__ == "__main__":
    main()
