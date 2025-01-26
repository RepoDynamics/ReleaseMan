from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

import pylinks as pl
from loggerman import logger

from releaseman import file_archiver

if TYPE_CHECKING:
    from github_contexts import GitHubContext
    from releaseman.dstruct import Token
    from releaseman.report import Reporter


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
            self._remove_files(release_id)
            self._add_files(release_id)
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
        self._add_files(release_response["id"])
        return

    def _remove_files(self, release_id: int):
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

    def _add_files(self, release_id: int):
        assets = self.config.get("assets")
        if not assets:
            logger.info(
                "GitHub Asset Upload",
                "No assets provided."
            )
            return
        for asset in assets:
            filepath, mime_type = file_archiver.make(
                root_path=self.path_root,
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
