"""The in-dashboard documentation: the Markdown files in docs/, listed by docs/nav.json."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..deps import AppContext, current_session, get_ctx

router = APIRouter(tags=["docs"])


def _nav(ctx: AppContext) -> dict:
    try:
        return json.loads((ctx.cfg.docs_dir / "nav.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(503, detail={"message": "the documentation is not installed on this server"})


@router.get("/docs")
def docs_index(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return _nav(ctx)


@router.get("/docs/{slug}")
def docs_page(slug: str, ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    # Only files named in nav.json can be read, so the slug never becomes a path
    for group in _nav(ctx).get("groups", []):
        for page in group.get("pages", []):
            if page.get("slug") == slug:
                try:
                    text = (ctx.cfg.docs_dir / page["file"]).read_text(encoding="utf-8")
                except OSError:
                    break
                return {"slug": slug, "title": page["title"], "markdown": text}
    raise HTTPException(404, detail={"message": f"no documentation page called '{slug}'"})
