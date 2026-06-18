from pathlib import Path

from agent_template_builder.exporters.agent_rows import AgentRowsExporter
from agent_template_builder.pipeline.export_agent_rows import export_agent_rows, to_index_value_data
from agent_template_builder.schema.agent_data import AgentData, Element, Resolution, RuntimeState, Screen
from agent_template_builder.schema.agent_rows import load_agent_rows_config


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
FIELDS_CONFIG = ROOT / "agent_fields.json"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc"


def test_agent_fields_config_loads_with_unique_indexes_and_keys() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)

    indexes = [field.index for field in config.fields]
    keys = [field.key for field in config.fields]

    assert config.schema == "dhxy2_classic_pc.agent_rows.v1"
    assert len(indexes) == len(set(indexes))
    assert len(keys) == len(set(keys))


def test_agent_rows_are_sorted_and_missing_values_are_empty() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = AgentData(
        game={"id": "dhxy2", "client": "classic_pc"},
        screen=Screen(
            type="main_world",
            template_id="dhxy2_classic_main_world_v1",
            confidence=0.9,
            resolution=Resolution(width=1280, height=720),
        ),
        elements=[],
        state=RuntimeState(blocking_modal=False),
    )

    output = AgentRowsExporter(config).export(data)

    assert [row.index for row in output.rows] == sorted(row.index for row in output.rows)
    assert all(row.value == "" for row in output.rows)


def test_required_semantic_role_mappings_exist() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    roles = set(config.mappings.values())

    assert {
        "current_task",
        "dialog_text",
        "dialog_options",
        "battle_status",
        "panel_title",
        "reward_text",
        "reward_items",
    }.issubset(roles)


def test_exporter_maps_element_text_to_configured_indexes() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = AgentData(
        game={"id": "dhxy2", "client": "classic_pc"},
        screen=Screen(
            type="npc_dialog",
            template_id="dhxy2_classic_npc_dialog_v1",
            confidence=0.88,
            resolution=Resolution(width=1280, height=720),
        ),
        elements=[
            Element(
                id="dialog_body",
                type="text_region",
                bbox=(1, 2, 3, 4),
                confidence=0.8,
                semantic_role="dialog_text",
                text="hello npc",
            ),
            Element(
                id="dialog_options",
                type="text_region",
                bbox=(5, 6, 7, 8),
                confidence=0.8,
                semantic_role="dialog_options",
                text="accept quest",
            ),
            Element(
                id="reward_notice",
                type="text_region",
                bbox=(9, 10, 11, 12),
                confidence=0.8,
                semantic_role="reward_text",
                text="reward gained",
            ),
        ],
        state=RuntimeState(blocking_modal=False),
    )

    rows = {row.index: row.value for row in AgentRowsExporter(config).export(data).rows}

    assert rows[6] == "hello npc"
    assert rows[7] == "accept quest"
    assert rows[5000] == "reward gained"
    assert rows[12] == ""


def test_real_sample_exports_agent_rows() -> None:
    screenshot = SAMPLES_DIR / "screenshots" / "reward_popup__manual_summon_reward1.png"

    output = export_agent_rows(screenshot, GAME_DIR, FIELDS_CONFIG)
    row_indexes = {row.index for row in output.rows}

    assert output.schema == "dhxy2_classic_pc.agent_rows.v1"
    assert output.screen_type == "reward_popup"
    assert {3, 4, 6, 7, 12, 13, 5000, 5001}.issubset(row_indexes)


def test_cli_data_shape_is_index_to_value_only() -> None:
    screenshot = SAMPLES_DIR / "screenshots" / "reward_popup__manual_summon_reward1.png"

    output = export_agent_rows(screenshot, GAME_DIR, FIELDS_CONFIG)
    data = to_index_value_data(output)

    assert data == {
        "3": "",
        "4": "",
        "6": "",
        "7": "",
        "12": "",
        "13": "",
        "5000": "",
        "5001": "",
    }
