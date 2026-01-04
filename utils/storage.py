import json
from pathlib import Path

DEFAULT_GUILD_CONFIG = {
    "lang": "ja",

    "jl": {
        "enabled": False,
        "filter": {"ignore_bots": True},
        "channel_join": "",
        "channel_leave": "",
        "join_embed": {
            "title": "ようこそ！",
            "description": "{user} さん、参加ありがとう！",
            "color": "#57F287",
            "footer": {"text": "", "icon_url": ""},
        },
        "leave_embed": {
            "title": "またね！",
            "description": "{user} さんが退出しました。",
            "color": "#ED4245",
            "footer": {"text": "", "icon_url": ""},
        },
        "fields": {
            "show_id": True,
            "show_created_at": True,
            "show_join_order": False,
            "show_member_count": True,
            "show_avatar": True
        }
    },

    "ticket": {
        "limits": {"max_open_per_user": 5, "cooldown_minutes": 30},
        "auto": {"closed_delete_days": 14, "inactivity_delete_hours": 0},
        "log_channel_id": "",
        "panels": [
            {
                "panel_id": "default",
                "panel_name": "質問",
                "enabled": True,
                "mode": "channel",  # channel/thread
                "name_template": "ticket-{count}-{user_id}",
                "create_message": "内容を送ってください。必要なら参考画像も添付OKです。",
                "rules_embed": {
                    "title": "ルール / 注意事項",
                    "description": "誹謗中傷は禁止です。\n必要な情報をできるだけ詳しく書いてください。",
                    "color": "#5865F2",
                    "footer": {"text": "", "icon_url": ""}
                },
                "staff_role_ids": [],
                "close_category_id": "",
                "reopen_enabled": True,
                "modal": {
                    "enabled": True,
                    "genre_label": "ジャンル",
                    "body_label": "本文",
                    "urgency_label": "緊急度",
                    "allow_reference_image": True
                },
                "embed": {
                    "title": "サポート",
                    "description": "下のボタンからチケットを作成できます。",
                    "button_label": "チケット作成",
                    "color": "#5865F2"
                },
                # ✅設置済みメッセージ追跡（deployで自動追記）
                "deployments": []  # [{"channel_id":"...", "message_id":"..."}]
            }
        ]
    },

    "rank": {
        "enabled": True,
        "cooldown": 60,
        "embed": {
            "title": "ランク - {user}",
            "description": "あなたの現在のランク情報です。",
            "color": "#6D7CFF",
            "fields": [
                {"name": "テキスト", "value": "{text_count}", "inline": True},
                {"name": "VC", "value": "{vc_time}", "inline": True},
                {"name": "総合", "value": "{overall_score}", "inline": True}
            ],
            "footer": {"text": "", "icon_url": ""}
        },

        # ✅リーダーボード常時更新
        "leaderboard": {
            "enabled": False,
            "channel_id": "",
            "interval_minutes": 10,
            "message_id": ""  # deploy時に保存（再起動後も編集更新する）
        }
    }
}

def deep_merge(default, data):
    out = dict(default)
    for k, v in data.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def guild_config_path(guild_id):
    return Path("settings/guilds/{}/config.json".format(guild_id))

def load_guild_config(guild_id):
    p = guild_config_path(guild_id)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not p.exists():
        save_guild_config(guild_id, DEFAULT_GUILD_CONFIG)
        return dict(DEFAULT_GUILD_CONFIG)

    try:
        raw = p.read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw else {}
        merged = deep_merge(DEFAULT_GUILD_CONFIG, data)

        # panels最低1保証
        panels = merged.get("ticket", {}).get("panels", [])
        if not isinstance(panels, list) or len(panels) == 0:
            merged["ticket"]["panels"] = list(DEFAULT_GUILD_CONFIG["ticket"]["panels"])

        # deployments型保証
        for p2 in merged["ticket"]["panels"]:
            if "deployments" not in p2 or not isinstance(p2["deployments"], list):
                p2["deployments"] = []

        save_guild_config(guild_id, merged)
        return merged
    except Exception:
        save_guild_config(guild_id, DEFAULT_GUILD_CONFIG)
        return dict(DEFAULT_GUILD_CONFIG)

def save_guild_config(guild_id, cfg):
    p = guild_config_path(guild_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
