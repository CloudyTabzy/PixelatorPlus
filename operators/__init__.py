from . import apply, assets, export, hybrid, material, plan, presets, render_result, utility

_modules = (apply, assets, export, hybrid, material, plan, presets, render_result, utility)


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
