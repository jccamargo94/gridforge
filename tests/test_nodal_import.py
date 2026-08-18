def test_egret_installed():
    import egret  # noqa: F401
    from egret.data.model_data import ModelData  # noqa: F401


def test_nodal_package_importable():
    import app.nodal  # noqa: F401
    import app.nodal.engine  # noqa: F401
    import app.nodal.network  # noqa: F401
    import app.nodal.settlement  # noqa: F401
