import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import json
import requests
from pathlib import Path

class Ranking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_data(self, gid, uid):
        p = Path(f"data/ranking/{gid}/{uid}.json")
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            d = {"xp": 0, "level": 1}
            p.write_text(json.dumps(d))
            return d
        return json.load(p.open())

    @app_commands.command(name="rank", description="ランクカードを表示")
    async def rank(self, interaction: discord.Interaction):
        await interaction.response.defer()
        gid, uid = str(interaction.guild.id), str(interaction.user.id)
        data = self.get_data(gid, uid)
        
        # 画像作成 (800x250)
        base = Image.new('RGB', (800, 250), color=(30, 31, 34))
        draw = ImageDraw.Draw(base)
        
        # サーバー名表示（真ん中上部）
        try:
            font_mid = ImageFont.load_default(size=30)
            server_name = interaction.guild.name
            draw.text((400, 30), server_name, fill=(200, 200, 200), anchor="mm", font=font_mid)
        except: pass

        # メインテキスト（大きく表示）
        try:
            font_lg = ImageFont.load_default(size=60)
            draw.text((50, 120), f"LEVEL {data['level']}", fill=(88, 101, 242), font=font_lg)
            draw.text((50, 190), f"XP {data['xp']}", fill=(255, 255, 255), font=ImageFont.load_default(size=35))
        except: pass

        # アイコン取得（右側）
        avatar_url = interaction.user.display_avatar.url
        response = requests.get(avatar_url)
        avatar_img = Image.open(io.BytesIO(response.content)).convert("RGBA")
        avatar_img = avatar_img.resize((150, 150))
        
        # 丸く切り抜き
        mask = Image.new("L", (150, 150), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, 150, 150), fill=255)
        
        base.paste(avatar_img, (600, 50), mask)

        with io.BytesIO() as out:
            base.save(out, format="PNG")
            out.seek(0)
            await interaction.followup.send(file=discord.File(out, "rank.png"))

async def setup(bot):
    await bot.add_cog(Ranking(bot))