from __future__ import annotations

from typing import TYPE_CHECKING
import functools
import io

import mdit
import htmp
from loggerman import logger, style
from mdit.target.rich import HeadingConfig, PanelConfig, StyleConfig, InlineHeadingConfig, RuleConfig
from rich.text import Text

from releaseman.dstruct import _TitledEmoji
from releaseman.exception import ReleaseManException

if TYPE_CHECKING:
    from typing import Literal


EMOJI = {
        "pass": _TitledEmoji("Passed", "✅"),
        "skip": _TitledEmoji("Skipped", "⏭️"),
        "fail": _TitledEmoji("Failed", "❌"),
        "warning": _TitledEmoji("Passed with Warning", "⚠️"),
    }


class Reporter:

    def __init__(self):
        self._info = {
            "github": {"name": "GitHub"},
            "zenodo": {"name": "Zenodo"},
        }
        for val in self._info.values():
            val["status"] = None
            val["summary"] = None
            val["body"] = mdit.block_container()
            val["section"] = mdit.section_container()
        return

    def add(
        self,
        name: str,
        status: Literal["pass", "fail", "skip", "warning"] | None = None,
        summary= None,
        body=None,
        section=None,
        section_is_container=False,
    ):
        data = self._info[name]
        if status:
            data["status"] = status
        if summary:
            data["summary"] = summary
        if body:
            data["body"].extend(body)
        if section:
            if section_is_container:
                for content, conditions in section.values():
                    data["section"].append(content, conditions=conditions)
            else:
                data["section"].extend(section)
        return

    @property
    def failed(self):
        return any(data["status"] == "fail" for data in self._info.values())

    def generate(self) -> tuple[str, str]:
        status_badge, summary_table = self._generate_summary()
        body = mdit.block_container(status_badge)
        body.extend(summary_table)
        section = self._generate_sections()
        target_config, output = make_sphinx_target_config()
        report = mdit.document(
            heading="Workflow Summary",
            body=body,
            section=section,
            target_configs_md={"sphinx": target_config},
        )
        gha_summary = report.source(target="github", filters=["short, github"], separate_sections=False)
        full_summary = report.render(target="sphinx", filters=["full"], separate_sections=False)
        logger.info(
            "Report Generation Logs",
            mdit.element.rich(Text.from_ansi(output.getvalue())),
        )
        return gha_summary, full_summary

    def _generate_summary(self) -> tuple[mdit.element.InlineImage, mdit.element.Table]:
        failed = False
        skipped = False
        table_rows = [["Pipeline", "Status", "Summary"]]
        for pipeline in self._info.values():
            status = pipeline["status"]
            if not status:
                continue
            if status == "fail":
                failed = True
            elif status == "skip":
                skipped = True
            status_emoji = EMOJI[status]
            row = [
                pipeline["name"],
                htmp.element.span(status_emoji.emoji, title=status_emoji.title),
                pipeline["summary"],
            ]
            table_rows.append(row)
        table = mdit.element.table(
            rows=table_rows,
            caption="Pipeline Summary",
            num_rows_header=1,
            align_table="center",
        )
        if failed:
            workflow_status = "fail"
            color="rgb(200, 0, 0)"
        elif skipped:
            workflow_status = "skip"
            color = "rgb(0, 0, 200)"
        else:
            workflow_status = "pass"
            color = "rgb(0, 200, 0)"
        workflow_status_emoji = EMOJI[workflow_status]
        status_badge = mdit.element.badge(
            service="static",
            args={"message": workflow_status_emoji.title},
            label="Status",
            style="for-the-badge",
            color=color,
        )
        return status_badge, table

    def _generate_sections(self) -> dict[str, mdit.Document]:
        sections = {}
        for section_id, data in self._info.items():
            if not (data["body"] or data["section"]):
                continue
            section_full = mdit.document(
                heading=data['name'],
                body=data["body"],
                section=data["section"],
            )
            sections[section_id] = section_full
        return sections


def initialize_logger(
    title_number: int | list[int],
):
    logger.initialize(
        realtime_levels=list(range(1, 7)),
        exit_code_critical=1,
        github=True,
        github_debug=True,
        title_number=title_number,
        level_style_debug=style.log_level(
            color="muted",
            icon="🔘",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(200, 255, 255), bold=True),
            ),
        ),
        level_style_success=style.log_level(
            color="success",
            icon="✅",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(0, 250, 0), bold=True),
            ),
        ),
        level_style_info=style.log_level(
            color="info",
            icon="ℹ️",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(0, 200, 255), bold=True),
            ),
        ),
        level_style_notice=style.log_level(
            color="warning",
            icon="⚠️",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(255, 230, 0), bold=True),
            ),
        ),
        level_style_warning=style.log_level(
            color="warning",
            icon="🚨",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(255, 185, 0), bold=True),
            ),
        ),
        level_style_error=style.log_level(
            color="danger",
            icon="🚫",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(255, 100, 50), bold=True),
            ),
        ),
        level_style_critical=style.log_level(
            color="danger",
            opened=True,
            icon="⛔",
            rich_config=PanelConfig(
                title_style=StyleConfig(color=(255, 30, 30), bold=True),
            ),
        ),
        target_configs_rich={
            "console": mdit.target.console(
                heading=(
                    HeadingConfig(
                        inline=InlineHeadingConfig(
                            style=StyleConfig(color=(255, 200, 255), bold=True),
                            rule=RuleConfig(style=StyleConfig(color=(250, 250, 230))),
                        )
                    ),
                    HeadingConfig(
                        inline=InlineHeadingConfig(
                            style=StyleConfig(color=(235, 160, 255), bold=True),
                            rule=RuleConfig(style=StyleConfig(color=(220, 220, 200))),
                        )
                    ),
                    HeadingConfig(
                        inline=InlineHeadingConfig(
                            style=StyleConfig(color=(215, 120, 255), bold=True),
                            rule=RuleConfig(style=StyleConfig(color=(190, 190, 170))),
                        )
                    ),
                    HeadingConfig(
                        inline=InlineHeadingConfig(
                            style=StyleConfig(color=(195, 80, 255), bold=True),
                            rule=RuleConfig(style=StyleConfig(color=(160, 160, 140))),
                        )
                    ),
                    HeadingConfig(
                        inline=InlineHeadingConfig(
                            style=StyleConfig(color=(175, 40, 255), bold=True),
                            rule=RuleConfig(style=StyleConfig(color=(130, 130, 110))),
                        )
                    ),
                    HeadingConfig(
                        inline=InlineHeadingConfig(
                            style=StyleConfig(color=(155, 0, 255), bold=True),
                            rule=RuleConfig(style=StyleConfig(color=(100, 100, 80))),
                        )
                    ),
                )
            )
        }
    )


def make_sphinx_target_config():
    output = io.StringIO()
    target_config = mdit.target.sphinx(
        renderer=functools.partial(
            mdit.render.sphinx,
            status=output,
            warning=output,
            config={
                "extensions": [
                    'myst_nb',
                    'sphinx_design',
                    'sphinx_togglebutton',
                    'sphinx_copybutton',
                    'sphinxcontrib.mermaid',
                    'sphinx_tippy',
                ],
                "myst_enable_extensions": [
                    "amsmath",
                    "attrs_inline",
                    "colon_fence",
                    "deflist",
                    "dollarmath",
                    "fieldlist",
                    "html_admonition",
                    "html_image",
                    "linkify",
                    "replacements",
                    "smartquotes",
                    "strikethrough",
                    "substitution",
                    "tasklist",
                ],
                "html_theme": "pydata_sphinx_theme",
                "html_theme_options": {
                    "pygments_light_style": "default",
                    "pygments_dark_style": "monokai",
                },
                "html_title": "ProMan Report",
            }
        )
    )
    return target_config, output
