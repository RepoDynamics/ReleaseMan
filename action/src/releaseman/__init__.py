from pathlib import Path

from rich.text import Text
import actionman as _actionman
import github_contexts as _github_contexts
from loggerman import logger as _logger
import mdit

from releaseman.main import ReleaseManager
from releaseman.dstruct import Token
from releaseman.exception import ReleaseManException
from releaseman.report import Reporter, make_sphinx_target_config

def run():
    _logger.section("Execution")
    reporter = Reporter()
    github_context = _github_contexts.github.create(
        context=_actionman.env_var.read(name="RD_RELEASEMAN__GITHUB_CONTEXT", typ=dict)
    )
    current_log_section_level = _logger.current_section_level
    release_manager = ReleaseManager(
        root_path=Path(_actionman.env_var.read(name="RD_RELEASEMAN__ROOT_PATH", typ=str)),
        output_path=Path(_actionman.env_var.read(name="RD_RELEASEMAN__OUTPUT_PATH", typ=str)),
        github_config=_actionman.env_var.read(name="RD_RELEASEMAN__GITHUB_CONFIG", typ=dict),
        zenodo_config=_actionman.env_var.read(name="RD_RELEASEMAN__ZENODO_CONFIG", typ=dict),
        github_token=Token(_actionman.env_var.read(name="RD_RELEASE__GITHUB_TOKEN", typ=str), name="GitHub"),
        zenodo_token=Token(_actionman.env_var.read(name="RD_RELEASEMAN__ZENODO_TOKEN", typ=str), name="Zenodo"),
        github_context=github_context,
        reporter=reporter,
    )
    try:
        release_manager.run()
    except ReleaseManException:
        _logger.section_end(target_level=current_log_section_level)
        _finalize(github_context=github_context, reporter=reporter)
        return
    except Exception as e:
        traceback = _logger.traceback()
        error_name = e.__class__.__name__
        _logger.critical(
            f"Unexpected Error: {error_name}",
            traceback,
        )
        reporter.add(
            "main",
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
        return
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
