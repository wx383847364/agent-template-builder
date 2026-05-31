from agent_template_builder.schema.agent_data import AgentData, Resolution, RuntimeState, Screen


def test_agent_data_to_dict() -> None:
    data = AgentData(
        game={"id": "dhxy2", "client": "classic_pc"},
        screen=Screen(
            type="main_world",
            template_id="dhxy2_classic_main_world_v1",
            confidence=0.9,
            resolution=Resolution(width=1280, height=720),
        ),
        elements=[],
        state=RuntimeState(blocking_modal=False, available_intents=["read_task"]),
    )

    result = data.to_dict()

    assert result["game"]["id"] == "dhxy2"
    assert result["screen"]["resolution"]["width"] == 1280
    assert result["state"]["available_intents"] == ["read_task"]

