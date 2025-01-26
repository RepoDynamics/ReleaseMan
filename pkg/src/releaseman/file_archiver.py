from __future__ import annotations

from typing import TYPE_CHECKING
import re
import shutil
import tempfile
import zipfile
import tarfile
import gzip
import bz2
import lzma
from pathlib import Path

if TYPE_CHECKING:
    from typing import Literal


MIME_TYPE = {
    'tar': "application/x-tar",
    'gz': "application/gzip",
    'bz2': "application/x-bzip2",
    'xz': "application/x-xz",
    "zip": "application/zip",
}
COMPRESSION_MODULE = {
    'gz': gzip,
    'bz2': bz2,
    'xz': lzma,
}


def make(
    root_path: Path,
    files: list[dict],
    out_dir: Path,
    name: str | None = None,
    output_format: Literal["zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "gz", "bz2", "xz"] | None = None,
) -> tuple[Path, str]:

    def copy(src: Path, dest: Path):
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest / src.name)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        for file_data in files:
            source_path = Path(file_data.get('source', "."))
            if not source_path.is_absolute():
                source_path = root_path / source_path
            destination_path = Path(temp_dir) / file_data.get('destination', '.')
            destination_path.mkdir(parents=True, exist_ok=True)
            pattern = file_data.get('pattern')
            if not pattern:
                copy(source_path, destination_path)
                continue
            source_paths = paths.setdefault(source_path, list(source_path.rglob('*')))
            for src_path in source_paths:
                if re.match(file_data['pattern'], src_path.relative_to(source_path).as_posix()):
                    copy(src_path, destination_path)
        copied_paths = list(Path(temp_dir).rglob('*'))
        if not copied_paths:
            raise ValueError('No files copied')
        if not output_format:
            if len(copied_paths) > 1 or copied_paths[0].is_dir():
                raise ValueError('Multiple files or directories copied, but no output format specified')
            final_path = out_dir / copied_paths[0].name
            shutil.copy2(copied_paths[0], final_path)
            return final_path, ""
        if not name:
            name = copied_paths[0].name
        archive_name = f"{name.removesuffix(f".{output_format}")}.{output_format}"
        archive_path = out_dir / archive_name
        if output_format == "zip":
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in copied_paths:
                    zipf.write(file_path, file_path.relative_to(temp_dir))
            return archive_path, MIME_TYPE[output_format]
        elif output_format in ['tar', 'tar.gz', 'tar.bz2', 'tar.xz']:
            parts = output_format.split('.')
            compression = parts[1] if len(parts) > 1 else None
            mode = f"w:{compression}" if compression else "w"
            with tarfile.open(archive_path, mode) as tar:
                tar.add(temp_dir, arcname='.')
            return archive_path, MIME_TYPE[compression or "tar"]
        elif len(copied_paths) > 1 or copied_paths[0].is_dir():
            raise ValueError('Multiple files or directories copied while using single file output format')
        compression_module = COMPRESSION_MODULE[output_format]
        with open(copied_paths[0], 'rb') as f_in, compression_module.open(archive_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        return archive_path, MIME_TYPE[output_format]
