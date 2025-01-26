from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

import pylinks as pl
from loggerman import logger

from releaseman import file_archiver

if TYPE_CHECKING:
    from releaseman.dstruct import Token
    from releaseman.report import Reporter


class ZenodoRelease:

    def __init__(
        self,
        root_path: Path,
        output_path: Path,
        config: dict,
        token: Token,
        sandbox: bool,
        reporter: Reporter,
    ):
        self.path_root = root_path
        self.path_out = output_path
        self.config = config
        self.reporter = reporter

        self.api = pl.api.zenodo(
            token=token.get(),
            sandbox=sandbox
        )
        try:
            self.api.deposition_list()
        except Exception as e:
            raise ValueError("Zenodo token is not valid") from e


        return

    def run(self):
        depo_id = self.config.get("deposition_id")
        metadata = self.config.get("metadata")
        if depo_id:
            depo_data = self.api.deposition_retrieve(deposition_id=depo_id)
            if depo_data["submitted"]:
                depo = self.api.deposition_new_version(deposition_id=depo_id)
            else:
                depo = depo_data
            if metadata:
                self.api.deposition_update(deposition_id=depo["id"], metadata=metadata)
            self.remove_files(depo)
        else:
            depo = self.api.deposition_create(metadata=metadata)
        self.add_files(depo)
        if self.config["publish"]:
            release_response = self.api.deposition_publish(deposition_id=depo["id"])
            logger.success(
                "Zenodo Release",
                str(release_response),
            )
        return

    def remove_files(self, deposition: dict):
        files_to_delete = self.config.get("delete_assets")
        if not files_to_delete:
            logger.info(
                "Zenodo Asset Deletion",
                "No assets provided."
            )
            return
        if isinstance(files_to_delete, list):
            old_filenames = [file["filename"] for file in deposition["files"]]
            for file_to_delete in files_to_delete:
                if file_to_delete not in old_filenames:
                    raise ValueError(
                        f"Cannot delete old version file '{file_to_delete}' as it does not exist."
                    )
            for old_file in deposition["files"]:
                if old_file["filename"] in files_to_delete:
                    self.api.file_delete(
                        deposition_id=deposition["id"],
                        file_id=old_file["id"]
                    )
        else:
            for old_file in deposition["files"]:
                self.api.file_delete(deposition_id=deposition["id"], file_id=old_file["id"])
        return

    def add_files(self, deposition: dict):
        assets = self.config.get("assets")
        if not assets:
            logger.info(
                "Zenodo Asset Upload",
                "No files provided."
            )
            return
        for asset in assets:
            filepath, _ = file_archiver.make(
                root_path=self.path_root,
                files=asset["files"],
                out_dir = self.path_out / "zenodo",
                name=asset.get("name"),
                output_format=asset.get("format"),
            )
            filename = asset.get("name", filepath.name)
            upload_response = self.api.file_create(
                bucket_id=deposition["links"]["bucket"],
                filepath=filepath,
                name=filename,
            )
            logger.info(
                f"Zenodo Asset Upload: {filename}",
                str(upload_response),
            )
        return


