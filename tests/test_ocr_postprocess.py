from pathlib import Path

from agent_template_builder.ocr.base import OCRResult
import pytest

from agent_template_builder.ocr.postprocess import OCRPostprocessor, load_confusions, load_vocab


def test_load_vocab_ignores_comments_blanks_bom_and_duplicates(tmp_path: Path) -> None:
    vocab_path = tmp_path / "terms.txt"
    vocab_path.write_text("\ufeff# terms\n任务\n\n 师门任务 \n任务\n", encoding="utf-8")

    assert load_vocab(vocab_path) == ("任务", "师门任务")


def test_server_name_correction_requires_an_explicit_server_role() -> None:
    processor = OCRPostprocessor(server_names=["雾隐云居"])
    original = OCRResult(text="雾隐云君", confidence=0.97)

    corrected = processor.process(original, "selected_server")
    unrelated = processor.process(original, "dialog_text")

    assert corrected.original is original
    assert corrected.original_text == "雾隐云君"
    assert corrected.corrected_text == "雾隐云居"
    assert corrected.changed is True
    assert unrelated.corrected_text == "雾隐云君"


def test_common_term_correction_requires_high_confidence_and_a_known_role() -> None:
    processor = OCRPostprocessor(common_terms=["师门任务"])
    high_confidence = OCRResult(text="领取师门任条后返回", confidence=0.95)
    low_confidence = OCRResult(text=high_confidence.text, confidence=0.89)

    corrected = processor.process(high_confidence, "current_task")

    assert corrected.corrected_text == "领取师门任务后返回"
    assert corrected.confidence == 0.95
    assert corrected.corrections[0].original == "师门任条"
    assert processor.process(low_confidence, "current_task").corrected_text == low_confidence.text
    assert processor.process(high_confidence, "system_notice").corrected_text == high_confidence.text


def test_ambiguous_vocabulary_candidates_do_not_change_text() -> None:
    processor = OCRPostprocessor(
        common_terms=["师门任务", "师门任意"],
        confusion_substitutions=[("条", "务"), ("条", "意")],
    )
    original = OCRResult(text="师门任条", confidence=0.99)

    result = processor.process(original, "current_task")

    assert result.corrected_text == original.text
    assert result.corrections == ()
    assert result.changed is False


def test_postprocessor_can_load_both_vocabularies_from_files(tmp_path: Path) -> None:
    server_names = tmp_path / "server_names.txt"
    common_terms = tmp_path / "common_terms.txt"
    server_names.write_text("雾隐云居\n", encoding="utf-8")
    common_terms.write_text("师门任务\n", encoding="utf-8")
    processor = OCRPostprocessor.from_files(
        server_names_path=server_names,
        common_terms_path=common_terms,
    )

    server = processor.process(OCRResult("雾隐云君", 0.95), "selected_server")
    task = processor.process(OCRResult("师门任条", 0.95), "current_task")

    assert server.corrected_text == "雾隐云居"
    assert task.corrected_text == "师门任务"


def test_short_production_terms_allow_one_unique_substitution() -> None:
    processor = OCRPostprocessor(
        server_names=["水晶宫"],
        common_terms=["任务", "师门", "召唤兽"],
    )

    task = processor.process(OCRResult("任条", 0.99), "current_task")
    summon = processor.process(OCRResult("召唤受", 0.99), "dialog_text")
    server = processor.process(OCRResult("水品宫", 0.99), "selected_server")

    assert task.corrected_text == "任务"
    assert summon.corrected_text == "召唤兽"
    assert server.corrected_text == "水晶宫"


def test_short_ambiguous_candidates_remain_unchanged() -> None:
    processor = OCRPostprocessor(
        common_terms=["任务", "任意"],
        confusion_substitutions=[("条", "务"), ("条", "意")],
    )

    result = processor.process(OCRResult("任条", 0.99), "current_task")

    assert result.corrected_text == "任条"
    assert result.corrections == ()


def test_short_terms_do_not_rewrite_valid_substrings_in_long_text() -> None:
    processor = OCRPostprocessor(common_terms=["长安", "师门", "洛阳"])

    examples = (
        "前往长寿村",
        "拜访师傅",
        "回到洛水镇",
    )

    assert [
        processor.process(OCRResult(text, 0.99), "current_task").corrected_text
        for text in examples
    ] == list(examples)


def test_directional_confusions_allow_embedded_terms_without_punctuation_false_positives() -> None:
    processor = OCRPostprocessor(common_terms=["任务", "召唤兽", "师门", "长安", "洛阳"])

    assert processor.process(OCRResult("领取任条后返回", 0.99), "current_task").corrected_text == "领取任务后返回"
    assert processor.process(OCRResult("选择召唤受出战", 0.99), "dialog_text").corrected_text == "选择召唤兽出战"
    assert processor.process(OCRResult("拜访：师傅", 0.99), "current_task").corrected_text == "拜访：师傅"
    assert processor.process(OCRResult("前往\n长寿", 0.99), "current_task").corrected_text == "前往\n长寿"
    assert processor.process(OCRResult("回到/洛水", 0.99), "current_task").corrected_text == "回到/洛水"


def test_server_list_correction_preserves_line_offsets() -> None:
    processor = OCRPostprocessor(server_names=["水晶宫", "爱你万年"])
    original = OCRResult("  水品宫\r\n爱你万年  ", 0.99)

    result = processor.process(original, "account_servers")

    assert result.corrected_text == "  水晶宫\r\n爱你万年  "
    assert result.corrections[0].start == 2
    assert result.corrections[0].end == 5


def test_npc_name_does_not_use_common_term_fuzzy_correction() -> None:
    processor = OCRPostprocessor(common_terms=["师门"])

    result = processor.process(OCRResult("师傅", 0.99), "npc_name")

    assert result.corrected_text == "师傅"
    assert result.corrections == ()


def test_load_confusions_validates_directional_single_characters(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(
        '{"version":1,"substitutions":[{"observed":"条","expected":"务"},'
        '{"observed":"条","expected":"务"}]}',
        encoding="utf-8",
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text(
        '{"version":1,"substitutions":[{"observed":"两字","expected":"务"}]}',
        encoding="utf-8",
    )

    assert load_confusions(valid) == (("条", "务"),)
    with pytest.raises(ValueError, match="single characters"):
        load_confusions(invalid)
