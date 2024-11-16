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
from loggerman import logger

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

        if self.config_zenodo:
            self.api_zenodo = pl.api.zenodo(
                token=self.zenodo_token.get(),
                sandbox=self.config_zenodo.get("sandbox", False)
            )
            try:
                self.api_zenodo.deposition_list()
            except Exception as e:
                raise ValueError("Zenodo token is not valid") from e

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



    def create_zenodo_deposition(self):
        depo_id = self.config_zenodo.get("deposition_id")
        metadata = self.config_zenodo.get("metadata")
        if depo_id:
            depo_data = self.api_zenodo.deposition_retrieve(deposition_id=depo_id)
            if depo_data["submitted"]:
                if not metadata:
                    raise ValueError("Metadata is not provided for new deposition.")
                depo = self.api_zenodo.deposition_new_version(deposition_id=depo_id)
            else:
                depo = depo_data
            if metadata:
                self.api_zenodo.deposition_update(deposition_id=depo["id"], metadata=metadata)
            self.remove_zenodo_files(depo)
        else:
            if not metadata:
                raise ValueError("Metadata is not provided for new deposition.")
            depo = self.api_zenodo.deposition_create(metadata=metadata)
        self.add_zenodo_files(depo)
        if self.config_zenodo["publish"]:
            release_response = self.api_zenodo.deposition_publish(deposition_id=depo["id"])
            logger.success(
                "Zenodo Release",
                str(release_response),
            )
        return

    def add_zenodo_files(self, deposition: dict):
        assets = self.config_zenodo.get("assets")
        if not assets:
            logger.info(
                "Zenodo Asset Upload",
                "No files provided."
            )
            return
        for asset in assets:
            filepath, _ = self.make_release_assets(
                files=asset["files"],
                out_dir = self.path_out / "zenodo",
                name=asset.get("name"),
                output_format=asset.get("format"),
            )
            filename = asset.get("name", filepath.name)
            upload_response = self.api_zenodo.file_create(
                bucket_id=deposition["links"]["bucket"],
                filepath=filepath,
                name=filename,
            )
            logger.info(
                f"Zenodo Asset Upload: {filename}",
                str(upload_response),
            )
        return

    def remove_zenodo_files(self, deposition: dict):
        files_to_delete = self.config_zenodo.get("delete_assets")
        if files_to_delete:
            if isinstance(files_to_delete, list):
                old_filenames = [file["filename"] for file in deposition["files"]]
                for file_to_delete in files_to_delete:
                    if file_to_delete not in old_filenames:
                        raise ValueError(
                            f"Cannot delete old version file '{file_to_delete}' as it does not exist."
                        )
                for old_file in deposition["files"]:
                    if old_file["filename"] in files_to_delete:
                        self.api_zenodo.file_delete(
                            deposition_id=deposition["id"],
                            file_id=old_file["id"]
                        )
            else:
                for old_file in deposition["files"]:
                    self.api_zenodo.file_delete(deposition_id=deposition["id"], file_id=old_file["id"])
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


class GitHubRelease:

    def __init__(
        self,
        root_path: Path,
        output_path: Path,
        config: dict,
        token: Token,
        reporter: Reporter,
        context: GitHubContext,
    ):
        self.path_root = root_path
        self.path_out = output_path
        self.config = config
        self.token = token
        self.reporter = reporter
        self.api = pl.api.github(
            token=token.get() or context.token
        ).user(
            config.get("repo_owner", context.repository_owner)
        ).repo(
            config.get("repo_name", context.repository_name)
        )
        return

    def run(self):
        release_id = self.config.get("release_id")
        release_data = {
            k: v for k, v in self.config.items()
            if k not in ("repo_owner", "repo_name", "release_id", "delete_assets", "assets") and v is not None
        }
        if release_id:
            self.remove_files(release_id)
            self.add_files(release_id)
            release_data.pop("generate_release_notes", None)
            if release_data:
                response = self.api.release_update(release_id=release_id, **release_data)
                logger.success(
                    "GitHub Release Update",
                    str(response)
                )
            return
        release_response = self.api.release_create(**release_data)
        logger.success(
            "GitHub Release Creation",
            str(release_response)
        )
        self.add_files(release_response["id"])
        return

    def remove_files(self, release_id: int):
        assets_to_del = self.config.get("delete_assets")
        if not assets_to_del:
            logger.info(
                "GitHub Asset Deletion",
                "No assets provided."
            )
            return
        asset_ids = [asset["id"] for asset in self.api.release_asset_list(release_id)]
        if isinstance(assets_to_del, list):
            for asset_to_del in assets_to_del:
                if asset_to_del not in asset_ids:
                    raise ValueError(
                        f"Cannot delete old version file '{asset_to_del}' as it does not exist."
                    )
            for asset_id in asset_ids:
                if asset_id in assets_to_del:
                    self.api.release_asset_delete(asset_id)
        else:
            for asset_id in asset_ids:
                self.api.release_asset_delete(asset_id)
        return

    def add_files(self, release_id: int):
        assets = self.config.get("assets")
        if not assets:
            logger.info(
                "GitHub Asset Upload",
                "No assets provided."
            )
            return
        for asset in assets:
            filepath, mime_type = self.make_release_assets(
                files=asset["files"],
                out_dir = self.path_out / "github",
                name=asset.get("name"),
                output_format=asset.get("format"),
            )
            filename = asset.get("name", filepath.name)
            upload_response = self.api.release_asset_upload(
                release_id=release_id,
                filepath=filepath,
                mime_type=mime_type or asset["media_type"],
                name=filename,
                label=asset.get("label", "")
            )
            logger.info(
                f"GitHub Asset Upload: {filename}",
                str(upload_response),
            )
        return
