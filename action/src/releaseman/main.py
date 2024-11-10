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

import pylinks as pl

if TYPE_CHECKING:
    from typing import Literal
    from github_contexts import GitHubContext
    from releaseman.dstruct import Token
    from releaseman.report import Reporter


class ReleaseManager:

    def __init__(
        self,
        root_path: Path,
        output_path: Path,
        github_config: dict,
        zenodo_config: dict,
        github_token: Token,
        zenodo_token: Token,
        github_context: GitHubContext,
        reporter: Reporter,
    ):
        self.path_root = root_path
        self.path_out = output_path
        self.config_gh = github_config
        self.config_zenodo = zenodo_config
        self.gh_token = github_token
        self.zenodo_token = zenodo_token
        self.gh_context = github_context
        self.reporter = reporter

        self.mime_type = {
            'tar': "application/x-tar",
            'gz': "application/gzip",
            'bz2': "application/x-bzip2",
            'xz': "application/x-xz",
            "zip": "application/zip",
        }
        self.compression_module = {
            'gz': gzip,
            'bz2': bz2,
            'xz': lzma,
        }
        return

    def run(self):
        if self.config_gh:
            self.create_github_release()
        if self.config_zenodo:
            self.create_zenodo_deposition()
        return

    def create_github_release(self):
        gh_api = pl.api.github(
            token=self.gh_token.get() or self.gh_context.token
        ).user(self.gh_context.repository_owner).repo(self.gh_context.repository_name)
        release_response = gh_api.release_create(
            tag_name=self.config_gh["tag_name"],
            name=self.config_gh["name"],
            body=self.config_gh["body"],
            draft=self.config_gh["draft"],
            prerelease=self.config_gh["prerelease"],
            discussion_category_name=self.config_gh["discussion_category_name"],
            make_latest=self.config_gh["make_latest"],
        )
        for asset_id, asset in self.config_gh["asset"].items():
            filepath, mime_type = self.make_release_assets(
                files=asset["files"],
                out_dir = self.path_out / "github",
                name=asset.get("name"),
                output_format=asset.get("output_format"),
            )
            upload_response = gh_api.release_asset_upload(
                release_id=release_response["id"],
                filepath=filepath,
                mime_type=mime_type or asset["media_type"],
                name=asset.get("name", filepath.name),
                label=asset.get("label", ""),
            )
        return

    def create_zenodo_deposition(self):
        zenodo_api = pl.api.zenodo(token=self.zenodo_token.get())
        for asset_id, asset in self.config_zenodo["asset"].items():
            filepath, _ = self.make_release_assets(
                files=asset["files"],
                out_dir = self.path_out / "zenodo",
                name=asset.get("name"),
                output_format=asset.get("output_format"),
            )
            upload_response = zenodo_api.file_create(
                bucket_url=self.config_zenodo["bucket_url"],
                filepath=filepath,
                upload_path=asset.get("name", filepath.name),
            )
        release_response = zenodo_api.deposition_publish(deposition_id=self.config_zenodo["deposition_id"])
        return

    def make_release_assets(
        self,
        files: list[dict],
        out_dir: Path,
        name: str | None = None,
        output_format: Literal[ "zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "gz", "bz2", "xz" ] | None = None,
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
                    source_path = self.path_root / source_path
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
                return archive_path, self.mime_type[output_format]
            elif output_format in ['tar', 'tar.gz', 'tar.bz2', 'tar.xz']:
                parts = output_format.split('.')
                compression = parts[1] if len(parts) > 1 else None
                mode = f"w:{compression}" if compression else "w"
                with tarfile.open(archive_path, mode) as tar:
                    tar.add(temp_dir, arcname='.')
                return archive_path, self.mime_type[compression or "tar"]
            elif len(copied_paths) > 1 or copied_paths[0].is_dir():
                raise ValueError('Multiple files or directories copied while using single file output format')
            compression_module = self.compression_module[output_format]
            with open(copied_paths[0], 'rb') as f_in, compression_module.open(archive_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            return archive_path, self.mime_type[output_format]
