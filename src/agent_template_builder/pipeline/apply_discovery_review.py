from __future__ import annotations

from pathlib import Path
import argparse
import json

from agent_template_builder.discovery.workflow import apply_discovery_review


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a human review to immutable DiscoveryData."
    )
    parser.add_argument("review", type=Path)
    args = parser.parse_args()

    reviewed_path, annotated_path = apply_discovery_review(args.review)
    print(
        json.dumps(
            {
                "reviewed": str(reviewed_path),
                "annotated": str(annotated_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
