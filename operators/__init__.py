from . import (
    apply, assets, export, hybrid, material, palette, plan, presets, render_result, sheet,
    utility,
)

_modules = (
    apply, assets, export, hybrid, material, palette, plan, presets, render_result, sheet,
    utility,
)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
