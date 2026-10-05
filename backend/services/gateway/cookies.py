"""HTTPS 与显式私网 HTTP 会话使用不同的主机 Cookie。"""

SESSION_COOKIE = "__Host-elect_session"
NONCE_COOKIE = "__Host-elect_browser"


def cookie_name(request, name):
    if request.app.state.public_origin.startswith("http://"):
        return name.removeprefix("__Host-") + "_local"
    return name


def get_cookie(request, name):
    return request.cookies.get(cookie_name(request, name))


def set_cookie(request, response, name, value, age):
    response.set_cookie(
        cookie_name(request, name), value, max_age=age,
        secure=request.app.state.public_origin.startswith("https://"),
        httponly=True, samesite="lax", path="/",
    )


def clear_cookie(request, response, name):
    response.delete_cookie(
        cookie_name(request, name),
        secure=request.app.state.public_origin.startswith("https://"),
        httponly=True, samesite="lax", path="/",
    )
