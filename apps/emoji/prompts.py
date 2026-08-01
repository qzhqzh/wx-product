from .models import EmojiItem, EmojiPack, PromptPreset

CATEGORY_ORDER = {
    PromptPreset.Category.BASE: 0,
    PromptPreset.Category.STYLE: 1,
    PromptPreset.Category.COMPOSITION: 2,
    PromptPreset.Category.QUALITY: 3,
    PromptPreset.Category.NEGATIVE: 4,
}


def prompt_context(item: EmojiItem) -> dict[str, str]:
    character_version = item.pack.project.character_version
    character = character_version.character.name if character_version else item.pack.name
    return {
        "character": character,
        "tone": item.pack.tone or "亲切有趣",
        "meaning": item.meaning,
        "copy_text": item.copy_text,
        "action": item.action,
    }


def render_prompt_snippet(content: str, context: dict[str, str]) -> str:
    rendered = content
    for key, value in context.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered.strip()


def selected_presets(pack: EmojiPack):
    return sorted(
        pack.prompt_presets.filter(is_active=True),
        key=lambda preset: (CATEGORY_ORDER[preset.category], preset.name),
    )


def compose_item_prompt(item: EmojiItem) -> tuple[str, str, list[str]]:
    context = prompt_context(item)
    positive_parts = [item.prompt.strip()]
    negative_parts = [item.pack.negative_prompt.strip()]
    preset_ids = []

    for preset in selected_presets(item.pack):
        preset_ids.append(str(preset.pk))
        rendered = render_prompt_snippet(preset.content, context)
        if not rendered:
            continue
        if preset.category == PromptPreset.Category.NEGATIVE:
            negative_parts.append(rendered)
        else:
            positive_parts.append(rendered)

    positive = "\n".join(part for part in positive_parts if part)
    negative = "；".join(part for part in negative_parts if part)
    return positive, negative, preset_ids


def attach_default_presets(pack: EmojiPack) -> None:
    defaults = PromptPreset.objects.filter(is_active=True, is_default=True)
    if defaults:
        pack.prompt_presets.add(*defaults)
