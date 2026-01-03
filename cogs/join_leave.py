import discord
from discord.ext import commands

class JoinLeave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_cfg(self, gid):
        return self.bot.get_cog("WebManager").get_guild_cfg(gid)

    def create_embed(self, data, member):
        text = json.dumps(data)
        for k, v in {
            "{user}": member.name, "{mention}": member.mention, 
            "{guild}": member.guild.name, "{member_count}": str(member.guild.member_count)
        }.items():
            text = text.replace(k, v)
        d = json.loads(text)
        emb = discord.Embed(
            title=d.get("title"), description=d.get("description"), color=d.get("color", 0x5865f2), url=d.get("url")
        )
        if d.get("image"): emb.set_image(url=d.get("image"))
        if d.get("thumbnail"): emb.set_thumbnail(url=d.get("thumbnail"))
        if d.get("footer"): emb.set_footer(text=d.get("footer"))
        return emb

    @commands.Cog.listener()
    async def on_member_join(self, member):
        cfg = self.get_cfg(member.guild.id)["jl"]
        if not cfg.get("enabled"): return
        if member.bot and cfg.get("ignore_bot"): return

        ch = member.guild.get_channel(int(cfg["channel_join"]))
        if ch:
            await ch.send(embed=self.create_embed(cfg["join_embed"], member))
        
        # 自動ロール
        if cfg.get("auto_role_id"):
            role = member.guild.get_role(int(cfg["auto_role_id"]))
            if role: await member.add_roles(role)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        cfg = self.get_cfg(member.guild.id)["jl"]
        if not cfg.get("enabled"): return
        ch = member.guild.get_channel(int(cfg["channel_leave"]))
        if ch:
            await ch.send(embed=self.create_embed(cfg["leave_embed"], member))

async def setup(bot):
    await bot.add_cog(JoinLeave(bot))