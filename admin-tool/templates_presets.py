"""漫剧三档渠道预设（对齐 docs/New-API渠道配置.md）。"""
from __future__ import annotations

from newapi_admin import (
    CHANNEL_TYPE_CUSTOM,
    CHANNEL_TYPE_OPENAI,
    CHANNEL_TYPE_VOLCENGINE,
    ChannelDraft,
)

ADAPTER_BASE = "http://seedance-adapter:18008"
VOLC_ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"

# 常用 Seedance 模型名（可按实际上游调整）
MODEL_MINI = "doubao-seedance-2-0-mini"
MODEL_FAST = "doubao-seedance-2-0-fast"
MODEL_FULL = "doubao-seedance-2-0"
MODEL_PRO = "doubao-seedance-2-5-pro"


def manga_triple_presets(
    *,
    volc_api_key: str,
    use_adapter: bool = True,
    aggregator_api_key: str = "",
    aggregator_base_url: str = "",
    aggregator_models: str = "",
) -> list[ChannelDraft]:
    """生成 draft/standard/final 推荐渠道列表。

    use_adapter=True：Base URL 指向 seedance-adapter（异步 Seedance 推荐）。
    类型用 Custom(8)；密钥填 ADAPTER 侧要求的 Bearer（常与 ADAPTER_API_TOKEN 相同）
    或填方舟 Key（若适配器只用自己的 VOLC_API_KEY，渠道 key 仍需非空——填 adapter token）。
    """
    if use_adapter:
        ch_type = CHANNEL_TYPE_CUSTOM
        base = ADAPTER_BASE
        # 渠道 key 会作为上游 Authorization；适配器校验 ADAPTER_API_TOKEN
        key = volc_api_key
    else:
        ch_type = CHANNEL_TYPE_VOLCENGINE
        base = VOLC_ARK_BASE
        key = volc_api_key

    drafts = [
        ChannelDraft(
            name="火山-mini(draft)",
            type=ch_type,
            key=key,
            models=MODEL_MINI,
            group="draft",
            base_url=base,
            weight=100,
            priority=1,
        ),
        ChannelDraft(
            name="火山-fast(standard)",
            type=ch_type,
            key=key,
            models=MODEL_FAST,
            group="standard",
            base_url=base,
            weight=100,
            priority=1,
        ),
        ChannelDraft(
            name="火山-2.0(final)",
            type=ch_type,
            key=key,
            models=MODEL_FULL,
            group="final",
            base_url=base,
            weight=100,
            priority=1,
        ),
        ChannelDraft(
            name="火山-2.5(final)",
            type=ch_type,
            key=key,
            models=MODEL_PRO,
            group="final",
            base_url=base,
            weight=90,
            priority=2,
        ),
    ]

    if aggregator_api_key and aggregator_base_url:
        models = aggregator_models.strip() or f"{MODEL_MINI},{MODEL_FAST}"
        drafts.append(
            ChannelDraft(
                name="聚合兜底(draft)",
                type=CHANNEL_TYPE_OPENAI,
                key=aggregator_api_key,
                models=models,
                group="draft",
                base_url=aggregator_base_url.rstrip("/"),
                weight=30,
                priority=5,
            )
        )
    return drafts


CHANNEL_TYPE_LABELS = {
    CHANNEL_TYPE_OPENAI: "OpenAI 兼容 (1)",
    CHANNEL_TYPE_CUSTOM: "Custom (8)",
    CHANNEL_TYPE_VOLCENGINE: "VolcEngine (45)",
}
