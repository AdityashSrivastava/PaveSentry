import starlette.routing
from fastapi import FastAPI

_orig_router_init = starlette.routing.Router.__init__
def _compat_router_init(self, *args, **kwargs):
    kwargs.pop("on_startup", None)
    kwargs.pop("on_shutdown", None)
    return _orig_router_init(self, *args, **kwargs)
starlette.routing.Router.__init__ = _compat_router_init

if not hasattr(starlette.routing.Router, "add_event_handler"):
    starlette.routing.Router.add_event_handler = lambda self, event_type, func: None

if not hasattr(FastAPI, "max_body_size"):
    FastAPI.max_body_size = None
