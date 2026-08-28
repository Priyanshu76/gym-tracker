"""
Small themed HTML confirmation pages for links that get clicked directly in
an email client (verify-email, approve-signup, reject-signup) rather than
called via fetch(). This is the same visual pattern as the old n8n version,
minus the Python-f-string/n8n-template brace collision that bit us there —
this is just a normal Python string, no competing template syntax involved.
"""
from fastapi.responses import HTMLResponse

_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><title>Gym Tracker</title>
<style>body{{font-family:sans-serif;background:#17181a;color:#f2efe7;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;}}
.box{{background:#1f2022;border:1px solid #35373a;border-radius:12px;padding:32px;max-width:400px;}}
h1{{font-size:20px;}} p{{color:#9aa0a6;font-size:14px;}}</style></head><body>
<div class="box"><h1>{title}</h1><p>{message}</p></div></body></html>"""


def confirmation_page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=_TEMPLATE.format(title=title, message=message),
        status_code=status_code,
        headers={"Content-Disposition": "inline"},
    )
