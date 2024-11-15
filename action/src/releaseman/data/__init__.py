from __future__ import annotations

from typing import TYPE_CHECKING

import jsonschemata
import pkgdata
import pyserials

if TYPE_CHECKING:
    from typing import Literal


_registry = jsonschemata.registry.make(dynamic=False, crawl=True)
_schema_dir_path = pkgdata.get_package_path_from_caller(top_level=False) / "schema"


def validate_schema(data: dict, name: Literal["github", "zenodo"]):
    schema = pyserials.read.json_from_file(_schema_dir_path / f"{name}-config.yaml")
    jsonschemata.edit.required_last(schema)
    pyserials.validate.jsonschema(
        data=data,
        schema=schema,
        registry=_registry,
        fill_defaults=True,
        iter_errors=True,
    )
    return
