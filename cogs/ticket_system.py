import asyncio
import logging
import json
import datetime
from pathlib import Path

import discord
from discord.ext import commands

from utils.storage import load_guild_config

logger = logging.getLogger("TicketSystem")

TICKET_DIR = Path("data/tickets")
TICKET_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_iso(s):
    try:
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1]
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def ticket_store_path(gid):
    return TICKET_DIR / f"{gid}.json"


def load_store(gid):
    p = ticket_store_path(gid)
    if not p.exists():
        p.write_text(json.dumps({"tickets": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "tickets" not in data or not isinstance(data["tickets"], list):
            return {"tickets": []}
        return data
    except Exception:
        return {"tickets": []}


def save_store(gid, data):
    p = ticket_store_path(gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def render(s, mp):
    s = str(s or "")
    for k, v in mp.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def color_from_hex(x, fallback=discord.Color.blurple()):
    try:
        return discord.Color(int(str(x).strip().lstrip("#"), 16))
    except Exception:
        return fallback


def build_embed(title, desc, color_hex, footer_text=""):
    e = discord.Embed(title=title or None, description=desc or None, color=color_from_hex(color_hex))
    if footer_text and str(footer_text).strip():
        e.set_footer(text=str(footer_text))
    return e


class TicketCreateSelectView(discord.ui.View):
    """Select(緊急度/ジャンル) → Modal(本文/画像URL) の2段階"""
    def __init__(self, cog, panel_index, types, urgency_choices, enable_genre, enable_urgency):
        super().__init__(timeout=120)
        self.cog = cog
        self.panel_index = panel_index
        self.enable_genre = enable_genre
        self.enable_urgency = enable_urgency
        self.types = types or []
        self.urgency_choices = urgency_choices or ["低い", "高い", "とても高い"]

        self.selected_type = self.types[0] if self.types else "質問"
        self.selected_urgency = self.urgency_choices[0] if self.urgency_choices else "低い"

        if self.enable_genre:
            self.type_select = discord.ui.Select(
                placeholder="ジャンルを選択",
                options=[discord.SelectOption(label=t, value=t) for t in self.types[:25]] or
                        [discord.SelectOption(label="質問", value="質問")]
            )
            self.type_select.callback = self._on_type
            self.add_item(self.type_select)

        if self.enable_urgency:
            self.urg_select = discord.ui.Select(
                placeholder="緊急度を選択",
                options=[discord.SelectOption(label=u, value=u) for u in self.urgency_choices[:25]]
            )
            self.urg_select.callback = self._on_urg
            self.add_item(self.urg_select)

        self.next_btn = discord.ui.Button(label="次へ（本文入力）", style=discord.ButtonStyle.primary)
        self.next_btn.callback = self._next
        self.add_item(self.next_btn)

    async def _on_type(self, interaction: discord.Interaction):
        self.selected_type = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)

    async def _on_urg(self, interaction: discord.Interaction):
        self.selected_urgency = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)

    async def _next(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketBodyModal(
            self.cog,
            self.panel_index,
            self.selected_type,
            self.selected_urgency
        ))


class TicketBodyModal(discord.ui.Modal):
    def __init__(self, cog, panel_index, selected_type, selected_urgency):
        super().__init__(title="お問い合わせ内容の入力")
        self.cog = cog
        self.panel_index = panel_index
        self.selected_type = selected_type
        self.selected_urgency = selected_urgency

        self.body = discord.ui.TextInput(label="本文", style=discord.TextStyle.paragraph, required=True, max_length=1500)
        self.image_url = discord.ui.TextInput(label="参考画像URL（任意）", required=False, max_length=300)

        self.add_item(self.body)
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, msg = await self.cog.create_ticket(
            interaction,
            self.panel_index,
            ticket_type=self.selected_type,
            urgency=self.selected_urgency,
            body=self.body.value,
            image_url=self.image_url.value
        )
        await interaction.followup.send(msg, ephemeral=True)


class CloseConfirmView(discord.ui.View):
    def __init__(self, cog, guild_id, ticket_id, panel_index):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.ticket_id = ticket_id
        self.panel_index = panel_index

    @discord.ui.button(label="クローズする", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, msg = await self.cog.close_ticket_by_id(interaction.guild, self.ticket_id, self.panel_index)
        # 二度押し防止
        for item in self.children:
            item.disabled = True
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("キャンセルしました。", ephemeral=True)


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cleanup_task = bot.loop.create_task(self._cleanup_loop())

    def cog_unload(self):
        try:
            self._cleanup_task.cancel()
        except Exception:
            pass

    async def deploy_panel(self, channel: discord.TextChannel, panel_index: int):
        cfg = load_guild_config(channel.guild.id)
        panel = cfg["ticket"]["panels"][panel_index]

        e = discord.Embed(
            title=f"🎫 {panel.get('panel_name','Ticket')}",
            description="下のボタンからチケットを作成できます。",
            color=discord.Color.blurple()
        )

        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(
            label="チケット作成",
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_create:{channel.guild.id}:{panel_index}"
        )
        btn.callback = self._create_button
        view.add_item(btn)
        msg = await channel.send(embed=e, view=view)
        return msg

    async def _create_button(self, interaction: discord.Interaction):
        try:
            _, gid, pidx = (interaction.data.get("custom_id") or "").split(":")
            panel_index = int(pidx)
        except Exception:
            await interaction.response.send_message("ボタン情報が壊れています。", ephemeral=True)
            return

        cfg = load_guild_config(interaction.guild.id)
        panel = cfg["ticket"]["panels"][panel_index]

        ok, reason = self._check_limits(interaction.guild.id, interaction.user.id, panel_index)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        # ---- 独立設定: 入力フォーム ----
        form = panel.get("form", {}) or {}
        enable_genre = bool(form.get("genre_enabled", True))
        enable_body = bool(form.get("body_enabled", True))
        enable_image = bool(form.get("image_enabled", True))
        enable_urgency = bool(form.get("urgency_enabled", True))
        urgency_choices = form.get("urgency_choices", ["低い", "高い", "とても高い"])

        types = panel.get("types", ["質問"])

        # Modalだけで完結させると緊急度プルダウンができないので Select→Modal にする
        if enable_body:
            await interaction.response.send_message(
                "入力内容を選んでください。",
                ephemeral=True,
                view=TicketCreateSelectView(
                    self, panel_index,
                    types=types,
                    urgency_choices=urgency_choices,
                    enable_genre=enable_genre,
                    enable_urgency=enable_urgency
                )
            )
            return

        # body無効（特殊）：最低限で作る
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, msg = await self.create_ticket(
            interaction, panel_index,
            ticket_type=types[0] if types else "質問",
            urgency=urgency_choices[0] if urgency_choices else "低い",
            body="(本文入力なし)",
            image_url=""
        )
        await interaction.followup.send(msg, ephemeral=True)

    def _check_limits(self, gid, uid, panel_index):
        cfg = load_guild_config(gid)
        panel = cfg["ticket"]["panels"][panel_index]
        lim = panel.get("limits", {}) or {}
        max_open = int(lim.get("max_open_per_user", 5))
        cooldown = int(lim.get("cooldown_minutes", 30))

        store = load_store(gid)
        open_count = 0
        last_created = None

        for t in store["tickets"]:
            if int(t.get("user_id", 0)) != int(uid):
                continue
            if int(t.get("panel_index", -1)) != int(panel_index):
                continue
            if t.get("status") in ("open", "pending"):
                open_count += 1
            dt = parse_iso(t.get("created_at"))
            if dt and (last_created is None or dt > last_created):
                last_created = dt

        if open_count >= max_open:
            return False, f"同時に持てるチケット数の上限（{max_open}件）に達しています。"

        if last_created:
            delta = datetime.datetime.utcnow() - last_created
            if delta.total_seconds() < cooldown * 60:
                m = int((cooldown * 60 - delta.total_seconds()) // 60) + 1
                return False, f"連続作成制限中です。あと約{m}分で作成できます。"

        return True, ""

    async def create_ticket(self, interaction: discord.Interaction, panel_index: int, ticket_type: str, urgency: str, body: str, image_url: str):
        guild = interaction.guild
        cfg = load_guild_config(guild.id)
        panel = cfg["ticket"]["panels"][panel_index]

        types = panel.get("types", []) or []
        if types and ticket_type not in types:
            ticket_type = types[0]

        # urgency choices
        form = panel.get("form", {}) or {}
        choices = form.get("urgency_choices", ["低い", "高い", "とても高い"])
        if urgency not in choices:
            urgency = choices[0] if choices else "低い"

        store = load_store(guild.id)
        count = 1 + sum(1 for t in store["tickets"] if int(t.get("panel_index", -1)) == panel_index)

        mapping = {
            "user": interaction.user.name,
            "user_id": interaction.user.id,
            "created_at": datetime.datetime.utcnow().strftime("%Y%m%d-%H%M"),
            "count": count,
            "type": ticket_type,
            "urgency": urgency
        }

        # ---- 作成方式 channel / thread ----
        mode = panel.get("mode", "channel")
        staff_ids = [int(x) for x in (panel.get("permissions", {}).get("staff_role_ids", []) or []) if str(x).isdigit()]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        for rid in staff_ids:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)

        created_channel_id = None
        created_thread_id = None

        if mode == "thread":
            parent_id = panel.get("thread_parent_channel_id", "")
            parent = guild.get_channel(int(parent_id)) if str(parent_id).isdigit() else interaction.channel
            if not isinstance(parent, discord.TextChannel):
                return False, "スレッド親チャンネルが不正です。"

            name = render(panel.get("name_template", "ticket-{count}-{user}"), mapping)[:90]
            thread = await parent.create_thread(name=name, type=discord.ChannelType.private_thread)
            created_thread_id = thread.id

            await thread.add_user(interaction.user)
            # staffはロールメンバーが多すぎると重いので最小限（運用で必要なら後で改善）
            target = thread

        else:
            cat_id = panel.get("parent_category_id", "")
            category = guild.get_channel(int(cat_id)) if str(cat_id).isdigit() else None
            if category and not isinstance(category, discord.CategoryChannel):
                category = None

            name = render(panel.get("name_template", "ticket-{count}-{user}"), mapping).lower().replace(" ", "-")[:90]
            ch = await guild.create_text_channel(name=name, category=category, overwrites=overwrites, reason="ticket create")
            created_channel_id = ch.id
            target = ch

        # ---- 投稿（テンプレ+ルールを同一Embedでセクション分け） ----
        post = panel.get("post", {}) or {}
        post_enabled = bool(post.get("enabled", True))
        layout = post.get("layout", "vertical")  # vertical / horizontal
        inline = (layout == "horizontal")

        if post_enabled:
            # テンプレ
            tsec = post.get("template_section", {}) or {}
            t_title = tsec.get("title", "📝 お問い合わせ内容")
            t_desc = tsec.get("description", "種別: {type}\n緊急度: {urgency}")

            # ルール
            rsec = post.get("rules_section", {}) or {}
            r_title = rsec.get("title", "📌 ルール/注意事項")
            r_desc = rsec.get("description", "個人情報は書かないでください。\n@everyoneは禁止です。")

            # 1 embed
            e = discord.Embed(
                title=f"🎫 {panel.get('panel_name','Ticket')}",
                color=discord.Color.blurple()
            )

            # “本文を```本文```でコピー可能に”
            body_block = "```{}\n```".format(body.strip()[:1800])

            e.add_field(
                name=render(t_title, mapping),
                value=render(t_desc, {**mapping, "type": ticket_type, "urgency": urgency}) + "\n\n本文:\n" + body_block,
                inline=inline
            )

            if image_url and str(image_url).strip():
                e.add_field(name="参考画像URL", value=str(image_url).strip(), inline=False)

            e.add_field(
                name=render(r_title, mapping),
                value=render(r_desc, mapping),
                inline=inline
            )

            await target.send(embed=e, view=self._ticket_control_view(guild.id, panel_index))
        else:
            # post無効なら最低限
            await target.send("チケットを作成しました。", view=self._ticket_control_view(guild.id, panel_index))

        ticket_id = f"{guild.id}-{panel_index}-{int(datetime.datetime.utcnow().timestamp()*1000)}"
        store["tickets"].append({
            "ticket_id": ticket_id,
            "panel_index": panel_index,
            "user_id": interaction.user.id,
            "status": "open",
            "type": ticket_type,
            "urgency": urgency,
            "created_at": now_iso(),
            "last_message_at": now_iso(),
            "channel_id": created_channel_id,
            "thread_id": created_thread_id
        })
        save_store(guild.id, store)

        return True, f"チケットを作成しました：{target.mention}"

    def _ticket_control_view(self, gid, panel_index):
        view = discord.ui.View(timeout=None)

        close_btn = discord.ui.Button(label="クローズ", style=discord.ButtonStyle.danger,
                                      custom_id=f"ticket_close:{gid}:{panel_index}")
        close_btn.callback = self._close_button
        view.add_item(close_btn)

        return view

    async def _close_button(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        cfg = load_guild_config(gid)

        try:
            _, _, pidx = (interaction.data.get("custom_id") or "").split(":")
            panel_index = int(pidx)
        except Exception:
            await interaction.response.send_message("パネル情報が不正です。", ephemeral=True)
            return

        panel = cfg["ticket"]["panels"][panel_index]
        store = load_store(gid)
        ticket = self._find_ticket_by_context(store, interaction.channel)

        if not ticket:
            await interaction.response.send_message("この場所はチケットとして登録されていません。", ephemeral=True)
            return

        # 2-4 確認ON時に正常にclose
        if panel.get("close", {}).get("confirm_required", True):
            await interaction.response.send_message(
                "本当にクローズしますか？",
                ephemeral=True,
                view=CloseConfirmView(self, gid, ticket["ticket_id"], panel_index)
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, msg = await self.close_ticket_by_id(interaction.guild, ticket["ticket_id"], panel_index)
        await interaction.followup.send(msg, ephemeral=True)

    async def close_ticket_by_id(self, guild, ticket_id, panel_index):
        cfg = load_guild_config(guild.id)
        panel = cfg["ticket"]["panels"][panel_index]
        store = load_store(guild.id)

        t = None
        for x in store["tickets"]:
            if x.get("ticket_id") == ticket_id:
                t = x
                break
        if not t:
            return False, "チケットが見つかりません。"

        # locate channel
        ch = None
        if t.get("channel_id"):
            ch = guild.get_channel(int(t["channel_id"]))
        if ch is None and t.get("thread_id"):
            ch = guild.get_thread(int(t["thread_id"])) if hasattr(guild, "get_thread") else None

        t["status"] = "closed"
        t["closed_at"] = now_iso()
        save_store(guild.id, store)

        if ch is None:
            return True, "クローズしました（対象が見つからないため記録のみ更新）。"

        closed_cat = str(panel.get("close", {}).get("closed_category_id", "")).strip()

        # カテゴリがあれば移動、なければ削除
        if closed_cat.isdigit() and isinstance(ch, discord.TextChannel):
            cat = guild.get_channel(int(closed_cat))
            if isinstance(cat, discord.CategoryChannel):
                try:
                    await ch.edit(category=cat, reason="ticket closed")
                    return True, "クローズしました（閉鎖カテゴリへ移動）。"
                except Exception:
                    logger.exception("failed to move closed ticket")

        try:
            await ch.delete(reason="ticket closed")
            return True, "クローズしました（削除）。"
        except Exception:
            logger.exception("failed to delete closed ticket")
            return True, "クローズしました（削除に失敗：権限を確認してください）。"

    def _find_ticket_by_context(self, store, channel_obj):
        cid = getattr(channel_obj, "id", None)
        if cid is None:
            return None
        for t in store["tickets"]:
            if t.get("channel_id") and int(t["channel_id"]) == int(cid):
                return t
            if t.get("thread_id") and int(t["thread_id"]) == int(cid):
                return t
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        store = load_store(message.guild.id)
        t = self._find_ticket_by_context(store, message.channel)
        if not t:
            return
        t["last_message_at"] = now_iso()
        save_store(message.guild.id, store)

    async def _cleanup_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                for g in list(self.bot.guilds):
                    await self._cleanup_guild(g)
            except Exception:
                logger.exception("cleanup loop error")
            await asyncio.sleep(60)

    async def _cleanup_guild(self, guild):
        cfg = load_guild_config(guild.id)
        store = load_store(guild.id)
        changed = False
        now = datetime.datetime.utcnow()

        for t in list(store["tickets"]):
            panel_index = int(t.get("panel_index", 0))
            panels = cfg.get("ticket", {}).get("panels", [])
            if panel_index < 0 or panel_index >= len(panels):
                continue
            panel = panels[panel_index]

            # inactive auto delete
            ad = panel.get("auto_delete", {}) or {}
            if ad.get("enabled", False) and t.get("status") in ("open", "pending"):
                mins = int(ad.get("inactive_minutes", 0))
                lm = parse_iso(t.get("last_message_at"))
                if mins > 0 and lm and (now - lm).total_seconds() > mins * 60:
                    await self._delete_if_exists(guild, t)
                    store["tickets"].remove(t)
                    changed = True
                    continue

            # delete closed after N days
            if t.get("status") == "closed":
                days = int(panel.get("close", {}).get("delete_after_days", 14))
                ca = parse_iso(t.get("closed_at"))
                if ca and (now - ca).days >= days:
                    await self._delete_if_exists(guild, t)
                    store["tickets"].remove(t)
                    changed = True

        if changed:
            save_store(guild.id, store)

    async def _delete_if_exists(self, guild, t):
        ch = None
        if t.get("channel_id"):
            ch = guild.get_channel(int(t["channel_id"]))
        if ch is None and t.get("thread_id"):
            ch = guild.get_thread(int(t["thread_id"])) if hasattr(guild, "get_thread") else None
        if ch:
            try:
                await ch.delete(reason="ticket cleanup")
            except Exception:
                logger.exception("cleanup delete failed")


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
