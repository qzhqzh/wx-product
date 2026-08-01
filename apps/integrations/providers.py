import base64
import io
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field


class ProviderConfigurationError(RuntimeError):
    pass


class ProviderCapabilityError(RuntimeError):
    pass


class SemanticItem(BaseModel):
    meaning: str = Field(max_length=12)
    copy_text: str = Field(max_length=20)
    action: str = Field(max_length=80)
    prompt: str = Field(max_length=600)


class SemanticPlan(BaseModel):
    summary: str = Field(max_length=500)
    items: list[SemanticItem]


@dataclass
class GeneratedMedia:
    content: bytes
    filename: str
    mime_type: str
    metadata: dict


class AIProvider(ABC):
    code: str
    text_model: str
    image_model: str
    supports_text = True
    supports_image = True

    @abstractmethod
    def plan_pack(self, *, name: str, brief: str, tone: str, count: int) -> SemanticPlan:
        raise NotImplementedError

    @abstractmethod
    def generate_image(
        self,
        *,
        prompt: str,
        meaning: str,
        order: int,
        reference: bytes | None = None,
        negative_prompt: str = "",
    ) -> GeneratedMedia:
        raise NotImplementedError

    def optimize_prompt(
        self,
        *,
        prompt: str,
        meaning: str,
        action: str,
        tone: str,
        negative_prompt: str = "",
    ) -> str:
        raise NotImplementedError


class LocalDemoProvider(AIProvider):
    code = "local"
    text_model = "local-semantic-v1"
    image_model = "local-sticker-v1"

    meanings = [
        ("收到", "收到！", "认真点头，双手比出确认动作"),
        ("开心", "好耶", "双手举高，眼睛弯成月牙"),
        ("疑问", "真的吗", "歪头并在头顶出现问号"),
        ("加油", "冲呀", "握拳向前，身体微微前倾"),
        ("感谢", "谢谢你", "双手合十，露出温柔笑容"),
        ("无语", "……", "半睁眼，身体定住"),
        ("抱歉", "对不起", "低头鞠躬，双手放在身前"),
        ("晚安", "睡啦", "抱着小枕头闭眼"),
        ("期待", "蹲一个", "双手托腮，眼睛发亮"),
        ("拒绝", "不可以", "双手交叉，坚定摇头"),
        ("惊讶", "哇！", "睁大眼睛，向后轻跳"),
        ("吃瓜", "看看", "抱着西瓜坐下围观"),
        ("忙碌", "马上来", "抱着文件快速奔跑"),
        ("得意", "拿捏", "叉腰抬头，露出小得意"),
        ("委屈", "呜呜", "眼角含泪，缩成一团"),
        ("再见", "回见", "挥手告别，向画面外移动"),
        ("赞同", "确实", "郑重点头并竖起拇指"),
        ("催促", "快点嘛", "看向手表，轻轻跺脚"),
        ("困惑", "没看懂", "左右张望，头顶冒出省略号"),
        ("安慰", "抱抱", "张开双臂向前拥抱"),
        ("庆祝", "开香槟", "抛出彩带，开心跳起"),
        ("生气", "气气", "鼓起脸颊，头顶冒出小火苗"),
        ("摸鱼", "歇会儿", "躺在小垫子上晃脚"),
        ("上线", "我来啦", "从画面边缘探头出现"),
    ]

    def plan_pack(self, *, name: str, brief: str, tone: str, count: int) -> SemanticPlan:
        items = []
        for index in range(count):
            meaning, copy_text, action = self.meanings[index % len(self.meanings)]
            items.append(
                SemanticItem(
                    meaning=meaning,
                    copy_text=copy_text,
                    action=action,
                    prompt=(
                        f"{name}角色，{tone or '亲切有趣'}，{action}。"
                        "微信表情贴纸风格，主体完整，透明背景，轮廓干净，无水印。"
                    ),
                )
            )
        return SemanticPlan(
            summary=brief or f"围绕{name}制作一套覆盖高频聊天场景的表情。",
            items=items,
        )

    def generate_image(
        self,
        *,
        prompt: str,
        meaning: str,
        order: int,
        reference: bytes | None = None,
        negative_prompt: str = "",
    ) -> GeneratedMedia:
        size = 1024
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        palette = [
            (224, 60, 74, 255),
            (37, 94, 132, 255),
            (232, 145, 42, 255),
            (76, 156, 112, 255),
        ]
        body = palette[order % len(palette)]
        phase = (order % 7) / 7 * math.tau
        offset_x = int(math.sin(phase) * 35)
        offset_y = int(math.cos(phase) * 25)
        box = (190 + offset_x, 185 + offset_y, 834 + offset_x, 829 + offset_y)
        draw.ellipse(box, fill=body)
        eye_y = 425 + offset_y
        draw.ellipse((365 + offset_x, eye_y, 425 + offset_x, eye_y + 72), fill=(30, 30, 35))
        draw.ellipse((600 + offset_x, eye_y, 660 + offset_x, eye_y + 72), fill=(30, 30, 35))
        mouth_y = 580 + offset_y
        if order % 3 == 0:
            draw.arc(
                (420 + offset_x, mouth_y - 15, 610 + offset_x, mouth_y + 100),
                start=5,
                end=175,
                fill=(255, 255, 255),
                width=24,
            )
        elif order % 3 == 1:
            draw.ellipse(
                (475 + offset_x, mouth_y, 550 + offset_x, mouth_y + 90),
                fill=(255, 255, 255),
            )
        else:
            draw.line(
                (455 + offset_x, mouth_y + 35, 575 + offset_x, mouth_y + 35),
                fill=(255, 255, 255),
                width=22,
            )
        draw.ellipse((785, 160, 890, 265), fill=(255, 255, 255), outline=body, width=16)
        draw.text((824, 190), str(order + 1), fill=body)
        out = io.BytesIO()
        canvas.save(out, format="PNG")
        return GeneratedMedia(
            content=out.getvalue(),
            filename=f"local-{order + 1:02d}.png",
            mime_type="image/png",
            metadata={"provider": self.code, "prompt": prompt, "meaning": meaning},
        )

    def optimize_prompt(
        self,
        *,
        prompt: str,
        meaning: str,
        action: str,
        tone: str,
        negative_prompt: str = "",
    ) -> str:
        parts = [
            prompt.strip(),
            f"聊天含义：{meaning}；动作：{action}；语气：{tone or '亲切有趣'}。",
            "主体完整居中，轮廓清楚，透明背景，适合微信聊天小尺寸展示。",
        ]
        if negative_prompt:
            parts.append(f"避免出现：{negative_prompt}。")
        return "\n".join(part for part in parts if part)


class OpenAIProvider(AIProvider):
    code = "openai"
    text_model = settings.OPENAI_TEXT_MODEL
    image_model = settings.OPENAI_IMAGE_MODEL

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ProviderConfigurationError("缺少 OPENAI_API_KEY，任务已保留，可配置后重试。")
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def plan_pack(self, *, name: str, brief: str, tone: str, count: int) -> SemanticPlan:
        response = self.client.responses.parse(
            model=self.text_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "你是微信表情包编剧。规划互不重复、适合真实聊天的高频语义。"
                        "不要使用名人、第三方 IP、政治宗教、二维码、水印或营销背书。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"专辑：{name}\n语气：{tone}\nBrief：{brief}\n"
                        f"必须返回恰好 {count} 个语义项。每项写短含义词、聊天文案、"
                        "动作描述和可用于透明背景贴纸生成的中文 prompt。"
                    ),
                },
            ],
            text_format=SemanticPlan,
        )
        plan = response.output_parsed
        if plan is None or len(plan.items) != count:
            raise RuntimeError("OpenAI 返回的语义项数量不符合目标数量。")
        return plan

    def generate_image(
        self,
        *,
        prompt: str,
        meaning: str,
        order: int,
        reference: bytes | None = None,
        negative_prompt: str = "",
    ) -> GeneratedMedia:
        full_prompt = (
            f"{prompt}\n聊天含义：{meaning}。保持角色设定一致。"
            "单一角色，主体居中，四周保留安全边距，透明背景，不要水印、二维码或边框。"
        )
        if negative_prompt:
            full_prompt += f"\n避免出现：{negative_prompt}。"
        if reference:
            image_file = io.BytesIO(reference)
            image_file.name = "reference.png"
            response = self.client.images.edit(
                model=self.image_model,
                image=image_file,
                prompt=full_prompt,
                background="transparent",
                output_format="png",
                input_fidelity="high",
            )
        else:
            response = self.client.images.generate(
                model=self.image_model,
                prompt=full_prompt,
                size="1024x1024",
                background="transparent",
                output_format="png",
            )
        data = response.data[0]
        if not data.b64_json:
            raise RuntimeError("OpenAI 图像接口没有返回图像数据。")
        return GeneratedMedia(
            content=base64.b64decode(data.b64_json),
            filename=f"openai-{order + 1:02d}.png",
            mime_type="image/png",
            metadata={"provider": self.code, "model": self.image_model},
        )

    def optimize_prompt(
        self,
        *,
        prompt: str,
        meaning: str,
        action: str,
        tone: str,
        negative_prompt: str = "",
    ) -> str:
        response = self.client.responses.create(
            model=self.text_model,
            instructions=(
                "你是表情包图像提示词编辑。保留用户创意，只补充角色一致性、动作、"
                "构图、透明背景和小尺寸可读性要求。只返回最终中文提示词。"
            ),
            input=(
                f"原提示词：{prompt}\n含义：{meaning}\n动作：{action}\n语气：{tone}\n"
                f"负向要求：{negative_prompt}"
            ),
        )
        optimized = response.output_text.strip()
        if not optimized:
            raise RuntimeError("OpenAI 没有返回优化后的提示词。")
        return optimized


class QwenProvider(AIProvider):
    code = "qwen"
    text_model = settings.QWEN_TEXT_MODEL
    image_model = ""
    supports_image = False

    def __init__(self):
        if not settings.DASHSCOPE_API_KEY:
            raise ProviderConfigurationError(
                "缺少 DASHSCOPE_API_KEY；请使用百炼按量付费 API Key，"
                "不要使用仅限交互式工具的 Coding Plan 或 Token Plan Key。"
            )
        from openai import OpenAI

        self.client = OpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=settings.QWEN_BASE_URL,
        )

    def plan_pack(self, *, name: str, brief: str, tone: str, count: int) -> SemanticPlan:
        completion = self.client.chat.completions.create(
            model=self.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是微信表情包编剧。输出严格 JSON，结构为 "
                        '{"summary":"...", "items":[{"meaning":"", "copy_text":"", '
                        '"action":"", "prompt":""}]}。不要输出 Markdown。'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"专辑：{name}\n语气：{tone}\nBrief：{brief}\n"
                        f"生成恰好 {count} 个互不重复的高频聊天语义项。"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or ""
        plan = SemanticPlan.model_validate_json(content)
        if len(plan.items) != count:
            raise RuntimeError("Qwen 返回的语义项数量不符合目标数量。")
        return plan

    def generate_image(
        self,
        *,
        prompt: str,
        meaning: str,
        order: int,
        reference: bytes | None = None,
        negative_prompt: str = "",
    ) -> GeneratedMedia:
        raise ProviderCapabilityError(
            "qwen3.7-plus 只输出文本，不能生图；请选择独立的图像生成模型。"
        )

    def optimize_prompt(
        self,
        *,
        prompt: str,
        meaning: str,
        action: str,
        tone: str,
        negative_prompt: str = "",
    ) -> str:
        completion = self.client.chat.completions.create(
            model=self.text_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是表情包图像提示词编辑。保留原意，补全角色一致性、动作、"
                        "构图、透明背景和小尺寸可读性；只返回最终中文提示词。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"原提示词：{prompt}\n含义：{meaning}\n动作：{action}\n"
                        f"语气：{tone}\n负向要求：{negative_prompt}"
                    ),
                },
            ],
        )
        optimized = (completion.choices[0].message.content or "").strip()
        if not optimized:
            raise RuntimeError("Qwen 没有返回优化后的提示词。")
        return optimized


def get_provider(code: str | None = None, *, capability: str | None = None) -> AIProvider:
    selected = code or settings.DEFAULT_AI_PROVIDER
    provider_class = {
        "local": LocalDemoProvider,
        "openai": OpenAIProvider,
        "qwen": QwenProvider,
    }.get(selected)
    if not provider_class:
        raise ProviderConfigurationError(f"未配置 AI Provider：{selected}")
    if capability == "image" and not provider_class.supports_image:
        raise ProviderCapabilityError(
            "qwen3.7-plus 只输出文本，不能生图；请选择独立的图像生成模型。"
        )
    return provider_class()
