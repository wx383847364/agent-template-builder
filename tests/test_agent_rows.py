from __future__ import annotations

from pathlib import Path

import pytest

from agent_template_builder.exporters.agent_rows import AgentRowsExporter
from agent_template_builder.matcher.template_matcher import UnsupportedResolutionError
from agent_template_builder.pipeline.export_agent_rows import export_agent_rows, to_index_value_data
from agent_template_builder.schema.agent_data import AgentData, Element, Resolution, RuntimeState, Screen
from agent_template_builder.schema.agent_rows import load_agent_rows_config


ROOT = Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "configs" / "games" / "dhxy2_classic_pc"
FIELDS_CONFIG = ROOT / "agent_fields.json"
SAMPLES_DIR = ROOT / "samples" / "dhxy2_classic_pc"

WATER_CRYSTAL_PALACE = "\u6c34\u6676\u5bab"
LOVE_YOU_FOREVER = "\u7231\u4f60\u4e07\u5e74"


def _data(
    *,
    screen_type: str = "main_world",
    template_id: str = "dhxy2_classic_main_world_v1",
    confidence: float = 0.9,
    elements: list[Element] | None = None,
    blocking_modal: bool = False,
    available_intents: list[str] | None = None,
) -> AgentData:
    return AgentData(
        game={"id": "dhxy2", "client": "classic_pc"},
        screen=Screen(
            type=screen_type,
            template_id=template_id,
            confidence=confidence,
            resolution=Resolution(width=1280, height=720),
        ),
        elements=elements or [],
        state=RuntimeState(
            blocking_modal=blocking_modal,
            available_intents=available_intents or [],
        ),
    )


def test_agent_fields_config_loads_with_unique_indexes_and_keys() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)

    indexes = [field.index for field in config.fields]
    keys = [field.key for field in config.fields]

    assert config.schema == "dhxy2_classic_pc.agent_rows.v1"
    assert len(indexes) == len(set(indexes))
    assert len(keys) == len(set(keys))


def test_agent_rows_are_sorted_and_missing_business_values_are_empty() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    output = AgentRowsExporter(config).export(_data())
    rows = {row.index: row.value for row in output.rows}

    assert [row.index for row in output.rows] == sorted(row.index for row in output.rows)
    assert rows[202] == "main_world"
    assert rows[203] == "dhxy2_classic_main_world_v1"
    assert rows[204] == "0.900"
    assert rows[4000] == "0"
    assert rows[8000] == ""
    assert all(
        row.value == ""
        for row in output.rows
        if row.index not in {202, 203, 204, 4000}
    )


def test_required_semantic_role_mappings_exist() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    roles = set(config.mappings.values())

    assert {
        "screen_type",
        "template_id",
        "screen_confidence",
        "start_game_button",
        "login_qr_code",
        "blocking_modal",
        "available_intents",
        "window_center_offset",
        "selected_server",
        "account_servers",
        "common_login_characters",
        "selected_character",
        "character_selection_list",
        "enter_game_button",
        "current_task",
        "dialog_text",
        "dialog_options",
        "battle_status",
        "panel_title",
        "reward_text",
        "reward_items",
    }.issubset(roles)


def test_exporter_maps_foreground_metadata_to_configured_indexes() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(available_intents=["read_task", "open_map"])

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows["202"] == "main_world"
    assert rows["203"] == "dhxy2_classic_main_world_v1"
    assert rows["204"] == "0.900"
    assert rows["4000"] == "0"
    assert rows["8000"] == "read_task;open_map"


def test_exporter_marks_blocking_modal_metadata() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(
        screen_type="blocking_modal",
        template_id="dhxy2_classic_blocking_modal_v1",
        blocking_modal=True,
    )

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows["4000"] == "1"


def test_empty_available_intents_are_omitted_but_false_blocking_modal_is_kept() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    output = AgentRowsExporter(config).export(_data(available_intents=[]))
    internal_rows = {row.index: row.value for row in output.rows}
    sparse_rows = to_index_value_data(output)

    assert internal_rows[8000] == ""
    assert "8000" not in sparse_rows
    assert sparse_rows["4000"] == "0"


def test_available_intents_must_use_stable_token_style() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(available_intents=["read_task", "OpenMap"])

    with pytest.raises(ValueError, match=r"\[a-z0-9_\]\+"):
        AgentRowsExporter(config).export(data)


def test_exporter_maps_element_text_to_configured_indexes() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(
        screen_type="npc_dialog",
        template_id="dhxy2_classic_npc_dialog_v1",
        confidence=0.88,
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
    )

    rows = {row.index: row.value for row in AgentRowsExporter(config).export(data).rows}

    assert rows[6] == "hello npc"
    assert rows[7] == "accept quest"
    assert rows[5000] == "reward gained"
    assert rows[12] == ""


def test_legacy_sample_is_rejected_for_agent_rows() -> None:
    screenshot = SAMPLES_DIR / "screenshots" / "reward_popup__manual_summon_reward1.png"

    with pytest.raises(UnsupportedResolutionError, match="unsupported_resolution"):
        export_agent_rows(screenshot, GAME_DIR, FIELDS_CONFIG)


def test_login_waterfall_exports_start_game_button_with_click_coordinates() -> None:
    screenshot = SAMPLES_DIR / "screenshots" / "登陆瀑布界面-1920x1080.png"

    output = export_agent_rows(screenshot, GAME_DIR, FIELDS_CONFIG)
    data = to_index_value_data(output)

    assert data["303"] == "开始游戏@[1350, 640, 1470, 760]"


def test_qr_login_exports_padded_qr_code_coordinates() -> None:
    screenshot = SAMPLES_DIR / "screenshots" / "登陆二维码扫码界面.png"

    output = export_agent_rows(screenshot, GAME_DIR, FIELDS_CONFIG)
    data = to_index_value_data(output)

    assert data["304"] == "二维码@[453, 398, 725, 669]"


def test_cli_data_shape_is_sparse_index_to_value_only() -> None:
    screenshot = SAMPLES_DIR / "screenshots" / "登陆二维码扫码界面.png"

    output = export_agent_rows(screenshot, GAME_DIR, FIELDS_CONFIG)
    data = to_index_value_data(output)

    assert data["202"] == "qr_login"
    assert data["203"] == "dhxy2_classic_qr_login_v1"
    assert data["204"].count(".") == 1
    assert len(data["204"].split(".")[1]) == 3
    assert data["4000"] == "0"
    assert data["8000"] == "read_qr_login_notice;refresh_qr_code;switch_login_style"
    assert all(isinstance(key, str) and isinstance(value, str) for key, value in data.items())


def test_cli_data_omits_empty_values() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    selected = f"{WATER_CRYSTAL_PALACE}@[1, 2, 3, 4]"
    data = _data(
        screen_type="server_select",
        template_id="dhxy2_classic_server_select_v1",
        confidence=0.88,
        elements=[
            Element(
                id="selected_server",
                type="text_region",
                bbox=(1, 2, 3, 4),
                confidence=0.8,
                semantic_role="selected_server",
                text=selected,
            ),
        ],
    )

    output = AgentRowsExporter(config).export(data)

    assert to_index_value_data(output) == {
        "202": "server_select",
        "203": "dhxy2_classic_server_select_v1",
        "204": "0.880",
        "3": selected,
        "400": selected,
        "4000": "0",
    }


def test_server_select_rows_keep_click_bboxes_in_values() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    selected = f"{WATER_CRYSTAL_PALACE}@[610, 700, 700, 730]"
    account_servers = f"{WATER_CRYSTAL_PALACE}@[120, 245, 275, 275];{LOVE_YOU_FOREVER}@[275, 245, 430, 275]"
    data = _data(
        screen_type="server_select",
        template_id="dhxy2_classic_server_select_v1",
        confidence=0.88,
        elements=[
            Element(
                id="selected_server",
                type="text_region",
                bbox=(610, 700, 700, 730),
                confidence=0.8,
                semantic_role="selected_server",
                text=selected,
            ),
            Element(
                id="account_servers",
                type="text_region",
                bbox=(120, 245, 430, 275),
                confidence=0.8,
                semantic_role="account_servers",
                text=account_servers,
            ),
        ],
    )

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows == {
        "202": "server_select",
        "203": "dhxy2_classic_server_select_v1",
        "204": "0.880",
        "3": selected,
        "400": selected,
        "401": account_servers,
        "4000": "0",
    }


def test_server_select_rows_bind_names_to_static_slot_bboxes() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(
        screen_type="server_select",
        template_id="dhxy2_classic_server_select_v1",
        confidence=0.88,
        elements=[
            Element(
                id="selected_server",
                type="text_region",
                bbox=(397, 729, 534, 772),
                confidence=0.8,
                semantic_role="selected_server",
                text=WATER_CRYSTAL_PALACE,
            ),
            Element(
                id="account_servers",
                type="text_region",
                bbox=(120, 245, 430, 275),
                confidence=0.8,
                semantic_role="account_servers",
                text=f"{WATER_CRYSTAL_PALACE}\n{LOVE_YOU_FOREVER}",
            ),
            Element(
                id="selected_server_slot",
                type="button_slot",
                bbox=(397, 729, 534, 772),
                confidence=0.88,
                semantic_role="selected_server_slot",
                text="",
            ),
            Element(
                id="account_server_slot_1",
                type="button_slot",
                bbox=(51, 207, 191, 247),
                confidence=0.88,
                semantic_role="account_server_slot",
                text="",
            ),
            Element(
                id="account_server_slot_2",
                type="button_slot",
                bbox=(205, 207, 346, 247),
                confidence=0.88,
                semantic_role="account_server_slot",
                text="",
            ),
        ],
    )

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows == {
        "202": "server_select",
        "203": "dhxy2_classic_server_select_v1",
        "204": "0.880",
        "3": f"{WATER_CRYSTAL_PALACE}@[397, 729, 534, 772]",
        "400": f"{WATER_CRYSTAL_PALACE}@[397, 729, 534, 772]",
        "401": f"{WATER_CRYSTAL_PALACE}@[51, 207, 191, 247];{LOVE_YOU_FOREVER}@[205, 207, 346, 247]",
        "4000": "0",
    }


def test_exporter_publishes_window_offset_only_when_it_exceeds_five_pixels() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data()
    object.__setattr__(data, "raw", {"calibration": {"offset": [6, -7]}})

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows["9000"] == "window_center_offset@[6, -7]"


def test_server_select_rows_export_each_common_login_character_bbox() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(
        screen_type="server_select",
        template_id="dhxy2_classic_server_select_v1",
        confidence=0.915,
        elements=[
            Element(
                id="common_login_character_1",
                type="button",
                bbox=(949, 288, 1146, 360),
                confidence=0.9,
                semantic_role="common_login_characters",
                text="绝情魔女|0转68级|女魔|水晶宫",
            ),
            Element(
                id="common_login_character_2",
                type="button",
                bbox=(949, 365, 1146, 437),
                confidence=0.9,
                semantic_role="common_login_characters",
                text="第二角色|1转100级|男人|爱你万年",
            ),
        ],
    )

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows["402"] == (
        "绝情魔女|0转68级|女魔|水晶宫@[949, 288, 1146, 360];"
        "第二角色|1转100级|男人|爱你万年@[949, 365, 1146, 437]"
    )


def test_character_select_rows_export_targets() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(
        screen_type="character_select",
        template_id="dhxy2_classic_character_select_v1",
        confidence=0.92,
        elements=[
            Element(
                id="character_slot_1",
                type="button",
                bbox=(951, 324, 1174, 391),
                confidence=0.9,
                semantic_role="character_selection_list",
                text="绝情魔女|0转68级|女魔",
            ),
            Element(
                id="character_slot_2",
                type="button",
                bbox=(988, 399, 1174, 464),
                confidence=0.9,
                semantic_role="character_selection_list",
                text="灵剑寻花|0转10级|女魔",
            ),
            Element(
                id="enter_game_button",
                type="button",
                bbox=(606, 723, 745, 758),
                confidence=0.92,
                semantic_role="enter_game_button",
                text="进入游戏",
            ),
        ],
    )

    rows = to_index_value_data(AgentRowsExporter(config).export(data))
    first = "绝情魔女|0转68级|女魔@[951, 324, 1174, 391]"
    second = "灵剑寻花|0转10级|女魔@[988, 399, 1174, 464]"

    assert rows["500"] == first
    assert rows["502"] == f"{first};{second}"
    assert rows["503"] == "进入游戏@[606, 723, 745, 758]"


def test_server_select_rows_replace_legacy_click_centers_with_static_slot_bboxes() -> None:
    config = load_agent_rows_config(FIELDS_CONFIG)
    data = _data(
        screen_type="server_select",
        template_id="dhxy2_classic_server_select_v1",
        confidence=0.88,
        elements=[
            Element(
                id="selected_server",
                type="text_region",
                bbox=(397, 729, 534, 772),
                confidence=0.8,
                semantic_role="selected_server",
                text=f"{WATER_CRYSTAL_PALACE}@466,750",
            ),
            Element(
                id="selected_server_slot",
                type="button_slot",
                bbox=(397, 729, 534, 772),
                confidence=0.88,
                semantic_role="selected_server_slot",
                text="",
            ),
        ],
    )

    rows = to_index_value_data(AgentRowsExporter(config).export(data))

    assert rows["3"] == f"{WATER_CRYSTAL_PALACE}@[397, 729, 534, 772]"
    assert rows["400"] == f"{WATER_CRYSTAL_PALACE}@[397, 729, 534, 772]"
