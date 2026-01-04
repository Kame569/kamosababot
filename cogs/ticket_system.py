import asyncio
import logging
import json
import datetime
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

from utils.storage import load_guild_config, save_guild_config

logger = logging.getLogger("TicketSystem")

TICKET_DIR = Path("data/tickets")
TICKET_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_iso(s):
    try:
        # 末尾Z対応
        if s.endswith("Z"):
            s = s[:-1]
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def render_template(s, mapping):
    s = str(s or "")
    for k, v in mapping.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def ticket_store_path(gid):
    return TICKET_DIR / ("{}.json".format(gid))


def load_ticket_store(gid):
    p = ticket_store_path(gid)
    if not p.exists():
        p.write_text(json.dumps({"tickets": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "tickets" not in data or not isinstance(data["tickets"], list):
            data = {"tickets": []}
        return data
    except Exception:
        return {"tickets": []}


def save_ticket_store(gid, data):
    p = ticket_store_path(gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_embed_from_cfg(embed_cfg, mapping):
    title = render_template(embed_cfg.get("title", ""), mapping)
    desc = render_template(embed_cfg.get("description", ""), mapping)
    color = embed_cfg.get("color", "#5865F2")
    try:
        c = int(color.strip("#"), 16)
        col = discord.Color(c)
    except Exception:
        col = discord.Color.blurple()

    e = discord.Embed(title=title, description=desc, color=col)
    footer = ""
    fobj = embed_cfg.get("footer", {}) or {}
    footer = render_template(fobj.get("text", ""), mapping)
    if footer.strip():
        e.set_footer(text=footer)
    return e


class CloseConfirmView(discord.ui.View):
    def __init__(self, cog, ticket_id, panel_index):
        super().__init__(timeout=60)
        self.cog = cog
        self.ticket_id = ticket_id
        self.panel_index = panel_index

    @discord.ui.button(label="クローズする", style=discord.ButtonStyle.danger)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=False)
        ok, msg = await self.cog.close_ticket_by_id(interaction.guild, self.ticket_id, self.panel_index)
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("キャンセルしました。", ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self, cog, guild_id, panel_index):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = int(guild_id)
        self.panel_index = int(panel_index)

        self.add_item(discord.ui.Button(
            label="チケット作成",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_create:{}:{}".format(self.guild_id, self.panel_index)
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="dummy", style=discord.ButtonStyle.secondary, disabled=True)
    async def _dummy(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass


class TicketCreateModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, panel_index, labels):
        super().__init__(title="チケット作成")
        self.cog = cog
        self.guild_id = int(guild_id)
        self.panel_index = int(panel_index)

        self.type_in = discord.ui.TextInput(label=labels.get("type", "ジャンル"), placeholder="例: 質問", required=True, max_length=30)
        self.body_in = discord.ui.TextInput(label=labels.get("body", "本文"), style=discord.TextStyle.paragraph, required=True, max_length=1500)
        self.urg_in = discord.ui.TextInput(label=labels.get("urgency", "緊急度 (Low/Med/High)"), placeholder="Low / Med / High", required=True, max_length=8)
        self.img_in = discord.ui.TextInput(label=labels.get("image", "参考画像URL（任意）"), required=False, max_length=300)

        self.add_item(self.type_in)
        self.add_item(self.body_in)
        self.add_item(self.urg_in)
        self.add_item(self.img_in)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        t = (self.type_in.value or "").strip()
        body = (self.body_in.value or "").strip()
        urg = (self.urg_in.value or "").strip()
        img = (self.img_in.value or "").strip()

        ok, msg = await self.cog.create_ticket(
            interaction, self.panel_index,
            ticket_type=t, body=body, urgency=urg, image_url=img
        )
        await interaction.followup.send(msg, ephemeral=True)


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
        panels = cfg.get("ticket", {}).get("panels", [])
        if panel_index < 0 or panel_index >= len(panels):
            raise ValueError("invalid panel_index")

        p = panels[panel_index]
        title = "🎫 {}".format(p.get("panel_name", "Ticket"))
        desc = "下のボタンからチケットを作成できます。"
        e = discord.Embed(title=title, description=desc, color=discord.Color.blurple())

        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(
            label="チケット作成",
            style=discord.ButtonStyle.primary,
            custom_id="ticket_create:{}:{}".format(channel.guild.id, panel_index)
        )
        btn.callback = self._create_button_callback
        view.add_item(btn)

        msg = await channel.send(embed=e, view=view)
        return msg

    async def _create_button_callback(self, interaction: discord.Interaction):
        try:
            cid = interaction.data.get("custom_id", "")
            _, gid, pidx = cid.split(":")
            panel_index = int(pidx)
        except Exception:
            await interaction.response.send_message("ボタン情報が壊れています。", ephemeral=True)
            return

        cfg = load_guild_config(interaction.guild.id)
        panel = cfg["ticket"]["panels"][panel_index]

        # 制限チェック
        ok, reason = self._check_limits(interaction.guild.id, interaction.user.id, panel_index)
        if not ok:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        # Modal ON
        if panel.get("modal", {}).get("enabled", True):
            labels = panel.get("modal", {}).get("labels", {}) or {}
            await interaction.response.send_modal(TicketCreateModal(self, interaction.guild.id, panel_index, labels))
            return

        # Modal OFF: デフォ値で作る（最低限）
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, msg = await self.create_ticket(interaction, panel_index, ticket_type="質問", body="(本文なし)", urgency="Low", image_url="")
        await interaction.followup.send(msg, ephemeral=True)

    def _check_limits(self, gid, uid, panel_index):
        store = load_ticket_store(gid)
        cfg = load_guild_config(gid)
        panel = cfg["ticket"]["panels"][panel_index]
        lim = panel.get("limits", {}) or {}
        max_open = int(lim.get("max_open_per_user", 5))
        cooldown = int(lim.get("cooldown_minutes", 30))

        open_count = 0
        last_created = None
        for t in store["tickets"]:
            if int(t.get("user_id", 0)) != int(uid):
                continue
            if int(t.get("panel_index", -1)) != int(panel_index):
                continue
            st = t.get("status", "open")
            if st in ("open", "pending"):
                open_count += 1
            if t.get("created_at"):
                dt = parse_iso(t["created_at"])
                if dt and (last_created is None or dt > last_created):
                    last_created = dt

        if open_count >= max_open:
            return False, "同時に持てるチケット数の上限（{}件）に達しています。".format(max_open)

        if last_created:
            delta = datetime.datetime.utcnow() - last_created
            if delta.total_seconds() < cooldown * 60:
                m = int((cooldown * 60 - delta.total_seconds()) // 60) + 1
                return False, "連続作成制限中です。あと約{}分で作成できます。".format(m)

        return True, ""

    async def create_ticket(self, interaction: discord.Interaction, panel_index: int, ticket_type: str, body: str, urgency: str, image_url: str):
        guild = interaction.guild
        cfg = load_guild_config(guild.id)
        panel = cfg["ticket"]["panels"][panel_index]

        # type validation
        types = panel.get("types", []) or []
        if types and ticket_type not in types:
            ticket_type = types[0]

        if urgency not in ("Low", "Med", "High"):
            urgency = "Low"

        store = load_ticket_store(guild.id)
        count = 1 + sum(1 for t in store["tickets"] if int(t.get("panel_index", -1)) == panel_index)

        mapping = {
            "user": interaction.user.name,
            "user_id": interaction.user.id,
            "created_at": datetime.datetime.utcnow().strftime("%Y%m%d-%H%M"),
            "count": count,
            "type": ticket_type,
            "urgency": urgency,
            "body": body
        }

        mode = panel.get("mode", "channel")
        staff_ids = [int(x) for x in (panel.get("permissions", {}).get("staff_role_ids", []) or []) if str(x).isdigit()]

        # permission base
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
            # parent channel
            parent_id = panel.get("thread_parent_channel_id", "")
            parent = None
            if str(parent_id).isdigit():
                parent = guild.get_channel(int(parent_id))
            if parent is None:
                # fallback: interaction channel
                parent = interaction.channel
            if not isinstance(parent, discord.TextChannel):
                return False, "スレッド親チャンネルが不正です。"

            # private thread
            name = render_template(panel.get("name_template", "ticket-{count}-{user}"), mapping)[:90]
            thread = await parent.create_thread(name=name, type=discord.ChannelType.private_thread)
            created_thread_id = thread.id

            # add members & staff
            await thread.add_user(interaction.user)
            for rid in staff_ids:
                role = guild.get_role(rid)
                if role:
                    for m in role.members[:30]:  # 過負荷回避（必要なら後で最適化）
                        try:
                            await thread.add_user(m)
                        except Exception:
                            pass

            target = thread

        else:
            # channel mode
            cat_id = panel.get("parent_category_id", "")
            category = None
            if str(cat_id).isdigit():
                category = guild.get_channel(int(cat_id))
                if not isinstance(category, discord.CategoryChannel):
                    category = None

            name = render_template(panel.get("name_template", "ticket-{count}-{user}"), mapping)
            name = name.lower().replace(" ", "-")[:90]

            ch = await guild.create_text_channel(name=name, category=category, overwrites=overwrites, reason="ticket create")
            created_channel_id = ch.id
            target = ch

        # rules embed
        if panel.get("rules_embed", {}).get("enabled", True):
            rules_cfg = panel.get("rules_embed", {})
            e_rules = build_embed_from_cfg(rules_cfg, mapping)
            await target.send(embed=e_rules)

        # open message embed
        if panel.get("open_message", {}).get("enabled", True):
            emb_cfg = panel.get("open_message", {}).get("embed", {}) or {}
            e_open = build_embed_from_cfg(emb_cfg, mapping)
            if image_url:
                e_open.add_field(name="参考画像", value=image_url, inline=False)
            await target.send(embed=e_open, view=self._ticket_control_view(guild.id, panel_index))

        # store ticket
        ticket_id = "{}-{}-{}".format(guild.id, panel_index, int(datetime.datetime.utcnow().timestamp() * 1000))
        item = {
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
        }
        store["tickets"].append(item)
        save_ticket_store(guild.id, store)

        return True, "チケットを作成しました：{}".format(target.mention)

    def _ticket_control_view(self, gid, panel_index):
        view = discord.ui.View(timeout=None)

        close_btn = discord.ui.Button(label="クローズ", style=discord.ButtonStyle.danger,
                                      custom_id="ticket_close:{}:{}".format(gid, panel_index))
        close_btn.callback = self._close_button_callback
        view.add_item(close_btn)

        reopen_btn = discord.ui.Button(label="再オープン", style=discord.ButtonStyle.secondary,
                                       custom_id="ticket_reopen:{}:{}".format(gid, panel_index))
        reopen_btn.callback = self._reopen_button_callback
        view.add_item(reopen_btn)

        return view

    async def _close_button_callback(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        cfg = load_guild_config(gid)

        try:
            _, _, pidx = interaction.data.get("custom_id", "").split(":")
            panel_index = int(pidx)
        except Exception:
            await interaction.response.send_message("パネル情報が不正です。", ephemeral=True)
            return

        panel = cfg["ticket"]["panels"][panel_index]
        store = load_ticket_store(gid)

        # このチャンネル/スレッドに紐づくticket_id探す
        ticket = self._find_ticket_by_context(store, interaction.channel)
        if not ticket:
            await interaction.response.send_message("この場所はチケットとして登録されていません。", ephemeral=True)
            return

        # confirm
        if panel.get("close", {}).get("confirm_required", True):
            await interaction.response.send_message(
                "本当にクローズしますか？",
                ephemeral=True,
                view=CloseConfirmView(self, ticket["ticket_id"], panel_index)
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=False)
        ok, msg = await self.close_ticket_by_id(interaction.guild, ticket["ticket_id"], panel_index)
        await interaction.followup.send(msg, ephemeral=True)

    async def close_ticket_by_id(self, guild, ticket_id, panel_index):
        cfg = load_guild_config(guild.id)
        panel = cfg["ticket"]["panels"][panel_index]
        store = load_ticket_store(guild.id)

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
            # fetch thread via guild
            ch = guild.get_thread(int(t["thread_id"])) if hasattr(guild, "get_thread") else None

        closed_cat_id = str(panel.get("close", {}).get("closed_category_id", "")).strip()

        # update status
        t["status"] = "closed"
        t["closed_at"] = now_iso()
        save_ticket_store(guild.id, store)

        if ch is None:
            return True, "クローズしました（対象チャンネルが見つからないため記録のみ更新）。"

        # move or delete
        if closed_cat_id.isdigit() and isinstance(ch, discord.TextChannel):
            cat = guild.get_channel(int(closed_cat_id))
            if isinstance(cat, discord.CategoryChannel):
                try:
                    await ch.edit(category=cat, reason="ticket closed")
                except Exception:
                    logger.exception("failed to move closed ticket")
            return True, "クローズしました（閉鎖カテゴリへ移動）。"

        # no closed category -> delete
        try:
            await ch.delete(reason="ticket closed (no closed category)")
        except Exception:
            logger.exception("failed to delete closed ticket channel/thread")
            return True, "クローズしました（削除に失敗：権限を確認してください）。"

        return True, "クローズしました（削除）。"

    async def _reopen_button_callback(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        cfg = load_guild_config(gid)

        try:
            _, _, pidx = interaction.data.get("custom_id", "").split(":")
            panel_index = int(pidx)
        except Exception:
            await interaction.response.send_message("パネル情報が不正です。", ephemeral=True)
            return

        panel = cfg["ticket"]["panels"][panel_index]
        if not panel.get("close", {}).get("allow_reopen", True):
            await interaction.response.send_message("このパネルは再オープンが無効です。", ephemeral=True)
            return

        store = load_ticket_store(gid)
        ticket = self._find_ticket_by_context(store, interaction.channel)
        if not ticket:
            await interaction.response.send_message("チケットが見つかりません。", ephemeral=True)
            return

        if ticket.get("status") != "closed":
            await interaction.response.send_message("closed 状態ではありません。", ephemeral=True)
            return

        ticket["status"] = "open"
        ticket["reopened_at"] = now_iso()
        save_ticket_store(gid, store)
        await interaction.response.send_message("再オープンしました（状態をopenに更新）。", ephemeral=True)

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
        gid = message.guild.id
        store = load_ticket_store(gid)
        t = self._find_ticket_by_context(store, message.channel)
        if not t:
            return
        t["last_message_at"] = now_iso()
        save_ticket_store(gid, store)

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
        store = load_ticket_store(guild.id)
        changed = False

        now = datetime.datetime.utcnow()

        for t in list(store["tickets"]):
            panel_index = int(t.get("panel_index", 0))
            panels = cfg.get("ticket", {}).get("panels", [])
            if panel_index < 0 or panel_index >= len(panels):
                continue
            panel = panels[panel_index]

            # inactive auto delete (open/pending only)
            ad = panel.get("auto_delete", {}) or {}
            if ad.get("enabled", False) and t.get("status") in ("open", "pending"):
                mins = int(ad.get("inactive_minutes", 0))
                if mins > 0:
                    lm = parse_iso(t.get("last_message_at", ""))
                    if lm and (now - lm).total_seconds() > mins * 60:
                        await self._delete_ticket_channel_if_exists(guild, t)
                        store["tickets"].remove(t)
                        changed = True
                        continue

            # delete closed after N days
            if t.get("status") == "closed":
                days = int(panel.get("close", {}).get("delete_after_days", 14))
                ca = parse_iso(t.get("closed_at", ""))
                if ca and (now - ca).days >= days:
                    await self._delete_ticket_channel_if_exists(guild, t)
                    store["tickets"].remove(t)
                    changed = True

        if changed:
            save_ticket_store(guild.id, store)

    async def _delete_ticket_channel_if_exists(self, guild, t):
        ch = None
        if t.get("channel_id"):
            ch = guild.get_channel(int(t["channel_id"]))
        if ch is None and t.get("thread_id"):
            ch = guild.get_thread(int(t["thread_id"])) if hasattr(guild, "get_thread") else None

        if ch:
            try:
                await ch.delete(reason="ticket cleanup")
            except Exception:
                logger.exception("failed to cleanup delete")

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))
