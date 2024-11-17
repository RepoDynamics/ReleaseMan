from pathlib import Path

from rich.text import Text
import actionman as _actionman
import github_contexts as _github_contexts
from loggerman import logger as _logger
import mdit

from releaseman.github import GitHubRelease
from releaseman.zenodo import ZenodoRelease
from releaseman.dstruct import Token
from releaseman.exception import ReleaseManException
from releaseman.report import Reporter, make_sphinx_target_config
from releaseman import data


def run():

    def run_manager(manager: GitHubRelease | ZenodoRelease):
        try:
            manager.run()
        except ReleaseManException:
            _logger.section_end(target_level=current_log_section_level)
            _finalize(github_context=github_context, reporter=reporter)
            return False
        except Exception as e:
            traceback = _logger.traceback()
            error_name = e.__class__.__name__
            _logger.critical(
                f"Unexpected Error: {error_name}",
                traceback,
            )
            reporter.add(
                "github" if isinstance(manager, GitHubRelease) else "zenodo",
                status="fail",
                summary=f"An unexpected error occurred: `{error_name}`",
                body=mdit.element.admonition(
                    title=error_name,
                    body=traceback,
                    type="error",
                    dropdown=True,
                    opened=True,
                ),
            )
            _logger.section_end(target_level=current_log_section_level)
            _finalize(github_context=github_context, reporter=reporter)
            return False
        return True

    _logger.section("Execution")
    reporter = Reporter()
    github_context = _github_contexts.github.create(
        context=_actionman.env_var.read(name="RD_RELEASEMAN__GITHUB_CONTEXT", typ=dict)
    )
    root_path = Path(_actionman.env_var.read(name="RD_RELEASEMAN__ROOT_PATH", typ=str))
    output_path = Path(_actionman.env_var.read(name="RD_RELEASEMAN__OUTPUT_PATH", typ=str))
    inputs = {}
    for env_var_segment, name, validation_name in (
        ("GITHUB", "GitHub", "github"),
        ("ZENODO", "Zenodo", "zenodo"),
        ("ZENODO_SANDBOX", "Zenodo Sandbox", "zenodo")
    ):
        token = Token(_actionman.env_var.read(name=f"RD_RELEASEMAN__{env_var_segment}_TOKEN", typ=str), name=name)
        config = _actionman.env_var.read(name=f"RD_RELEASEMAN__{env_var_segment}_CONFIG", typ=dict)
        if config:
            if not token and name != "GitHub":
                raise ValueError(f"{name} token not provided while config is provided.")
            data.validate_schema(config, validation_name)
            inputs[env_var_segment.lower()] = {"token": token, "config": config}

    current_log_section_level = _logger.current_section_level

    for release_type in ("zenodo_sandbox", "zenodo"):
        if release_type in inputs:
            _logger.section(release_type.replace("_", " ").title())
            release_manager = ZenodoRelease(
                root_path=root_path,
                output_path=output_path,
                sandbox=release_type == "zenodo_sandbox",
                reporter=reporter,
                **inputs[release_type]
            )
            success = run_manager(release_manager)
            if not success:
                return
            _logger.section_end()
    if "github" in inputs:
        _logger.section("GitHub Release")
        release_manager = GitHubRelease(
            root_path=root_path,
            output_path=output_path,
            reporter=reporter,
            context=github_context,
            **inputs["github"]
        )
        success = run_manager(release_manager)
        if not success:
            return
        _logger.section_end()
    _finalize(github_context=github_context, reporter=reporter)
    return


@_logger.sectioner("Output Generation")
def _finalize(github_context: _github_contexts.GitHubContext, reporter: Reporter):
    # output = output_writer.generate(failed=reporter.failed)
    # _write_step_outputs(output)

    report_gha, report_full = reporter.generate()
    _write_step_summary(report_gha)

    log = _logger.report
    target_config, output = make_sphinx_target_config()
    log.target_configs["sphinx"] = target_config
    log_html = log.render(target="sphinx")
    _logger.info(
        "Log Generation Logs",
        mdit.element.rich(Text.from_ansi(output.getvalue())),
    )
    filename = (
        f"{github_context.repository_name}-workflow-run"
        f"-{github_context.run_id}-{github_context.run_attempt}.{{}}.html"
    )
    dir_path = Path("uploads")
    dir_path.mkdir()
    with open(dir_path / filename.format("report"), "w") as f:
        f.write(report_full)
    with open(dir_path / filename.format("log"), "w") as f:
        f.write(log_html)
    return


def _write_step_outputs(kwargs: dict) -> None:
    log_outputs = []
    for name, value in kwargs.items():
        output_name = name.lower().replace("_", "-")
        written_output = _actionman.step_output.write(name=output_name, value=value)
        log_outputs.append(
            mdit.element.code_block(
                written_output,
                caption=f"{output_name} [{type(value).__name__}]",
            )
        )
    _logger.debug("GHA Step Outputs", *log_outputs)
    return


def _write_step_summary(content: str) -> None:
    _logger.debug("GHA Summary Output", mdit.element.code_block(content))
    _actionman.step_summary.write(content)
    return
