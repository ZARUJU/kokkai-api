"""cli.py の更新制御を検証するテスト。"""

from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

import cli


class CliMainTest(unittest.TestCase):
    """CLI の主な分岐を確認する。"""

    def test_parse_only_rebuilds_distribution_even_when_outputs_exist(self) -> None:
        """`--parse-only` では既存 data があっても再生成する。"""

        args = argparse.Namespace(
            sessions=[221],
            all=False,
            latest_count=2,
            force=False,
            parse_only=True,
            cleanup_tmp=False,
        )

        with (
            patch("cli.parse_args", return_value=args),
            patch("cli.run_pipeline_with_error_logging", return_value=None),
            patch("cli.run_distribution_builders") as run_distribution_builders,
            patch("cli.cleanup_tmp_artifacts"),
        ):
            cli.main()

        run_distribution_builders.assert_called_once_with(
            [221],
            skip_existing=False,
            blocked_targets=set(),
            skip_people_index=False,
        )

    def test_main_exits_nonzero_when_any_pipeline_failed(self) -> None:
        """一部失敗時は配布対象を絞って非0終了する。"""

        args = argparse.Namespace(
            sessions=[221],
            all=False,
            latest_count=2,
            force=False,
            parse_only=False,
            cleanup_tmp=False,
        )
        side_effects = [
            None,
            cli.PipelineFailure(pipeline_name="kaigiroku", session=221),
            None,
            None,
            None,
            None,
        ]

        with (
            patch("cli.parse_args", return_value=args),
            patch("cli.run_pipeline_with_error_logging", side_effect=side_effects),
            patch("cli.run_distribution_builders") as run_distribution_builders,
            patch("cli.cleanup_tmp_artifacts"),
        ):
            with self.assertRaises(SystemExit) as context:
                cli.main()

        self.assertEqual(str(context.exception), "一部の更新に失敗しました。ログを確認してください: kaigiroku:221")
        run_distribution_builders.assert_called_once_with(
            [221],
            skip_existing=True,
            blocked_targets={("kaigiroku", 221, None)},
            skip_people_index=True,
        )


if __name__ == "__main__":
    unittest.main()
