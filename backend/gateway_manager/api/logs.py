from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import AppContext, current_session, get_ctx

router = APIRouter(tags=["logs"])

SOURCES = ("access", "error", "admin-access", "admin-error", "nginx-error", "journal", "manager", "audit")


@router.get("/logs")
def logs(source: str = Query("access"), name: str = Query(""), lines: int = Query(200, ge=1, le=2000),
         filter: str = Query("", max_length=200), ctx: AppContext = Depends(get_ctx),
         session=Depends(current_session)):
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail={"message": f"unknown log source {source}"})
    if source == "audit":
        result = {"ok": True, "lines": ctx.audit.tail(lines)}
    else:
        if source in ("access", "error"):
            name = name or str(ctx.store.load().settings.gateway_port)
        elif source.startswith("admin-"):
            source, name = source[len("admin-"):], "admin"
        result = ctx.helper.logs(source, name, lines)
    if filter and result.get("ok"):
        needle = filter.lower()
        result["lines"] = [line for line in result.get("lines", []) if needle in line.lower()]
    return result
