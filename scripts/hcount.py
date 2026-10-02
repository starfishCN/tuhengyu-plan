import sys

P = "data.plugins.astrbot_plugin_tuhengyu"

try:
    import data.plugins.astrbot_plugin_tuhengyu.main as m  # noqa: F401
    from astrbot.core.star.star_handler import star_handlers_registry
except Exception as e:
    print("IMPORT_FAIL", type(e).__name__, e)
    sys.exit(1)

hs = [
    h
    for h in list(star_handlers_registry)
    if (getattr(h, "handler_module_path", "") or "").startswith(P)
]

print("HANDLERS", len(hs))
for h in hs:
    print("  %-16s %-28s %s" % (h.event_type, h.handler_name, h.handler_module_path))

mods = sorted({h.handler_module_path for h in hs})
print("MODULES", len(mods))
for x in mods:
    print("  ", x)