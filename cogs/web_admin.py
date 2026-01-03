import discord
from discord.ext import commands
from aiohttp import web
import json
import os
import asyncio

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Admin Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 text-white font-sans">
    <div class="flex h-screen">
        <!-- Sidebar -->
        <div class="w-64 bg-gray-800 p-6">
            <h1 class="text-2xl font-bold text-indigo-400 mb-8">Bot Admin</h1>
            <nav>
                <a href="/" class="block py-2.5 px-4 rounded transition duration-200 hover:bg-gray-700">Server List</a>
            </nav>
        </div>
        <!-- Main Content -->
        <div class="flex-1 p-10 overflow-y-auto">
            {content}
        </div>
    </div>
</body>
</html>
"""

class WebAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open("settings.json", "r") as f:
            self.web_conf = json.load(f)
        
        self.app = web.Application()
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/guild/{id}', self.handle_guild)
        self.app.router.add_post('/guild/{id}/update', self.handle_update)
        asyncio.create_task(self.start_server())

    async def start_server(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.web_conf['host'], self.web_conf['port'])
        await site.start()
        print(f"[WEB] Dashboard: http://localhost:{self.web_conf['port']}")

    async def handle_index(self, request):
        list_html = '<h2 class="text-3xl font-bold mb-6">管理サーバー一覧</h2><div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">'
        for guild in self.bot.guilds:
            list_html += f'''
            <div class="bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700">
                <h3 class="text-xl font-bold mb-2">{guild.name}</h3>
                <p class="text-gray-400 mb-4">ID: {guild.id}</p>
                <a href="/guild/{guild.id}" class="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg transition">設定を開く</a>
            </div>
            '''
        list_html += '</div>'
        return web.Response(text=HTML_TEMPLATE.format(content=list_html), content_type='text/html')

    async def handle_guild(self, request):
        gid = int(request.match_info['id'])
        conf = self.bot.get_guild_config(gid)
        guild = self.bot.get_guild(gid)
        
        form_html = f'''
        <h2 class="text-3xl font-bold mb-6">{guild.name} の設定</h2>
        <form action="/guild/{gid}/update" method="post" class="space-y-6">
            <div class="bg-gray-800 p-6 rounded-xl border border-gray-700">
                <h3 class="text-xl font-bold mb-4 border-b border-gray-700 pb-2">機能の有効化</h3>
                <div class="flex items-center space-x-4">
                    <label class="inline-flex items-center">
                        <input type="checkbox" name="f_ticket" {"checked" if conf['features']['ticket'] else ""} class="w-5 h-5 text-indigo-600">
                        <span class="ml-2">チケット機能</span>
                    </label>
                    <label class="inline-flex items-center">
                        <input type="checkbox" name="f_join" {"checked" if conf['features']['join_leave'] else ""} class="w-5 h-5 text-indigo-600">
                        <span class="ml-2">入退出通知</span>
                    </label>
                </div>
            </div>
            
            <div class="bg-gray-800 p-6 rounded-xl border border-gray-700">
                <h3 class="text-xl font-bold mb-4 border-b border-gray-700 pb-2">チケット設定</h3>
                <label class="block mb-2">ログ送信先チャンネルID</label>
                <input type="text" name="t_log_id" value="{conf['ticket']['log_channel_id'] or ''}" class="w-full bg-gray-700 border border-gray-600 rounded p-2">
            </div>

            <button type="submit" class="bg-green-600 hover:bg-green-700 text-white px-8 py-3 rounded-xl font-bold shadow-lg transition">設定を保存する</button>
        </form>
        '''
        return web.Response(text=HTML_TEMPLATE.format(content=form_html), content_type='text/html')

    async def handle_update(self, request):
        gid = int(request.match_info['id'])
        data = await request.post()
        conf = self.bot.get_guild_config(gid)
        
        # 値の更新
        conf['features']['ticket'] = 'f_ticket' in data
        conf['features']['join_leave'] = 'f_join' in data
        conf['ticket']['log_channel_id'] = data['t_log_id'] if data['t_log_id'] else None
        
        self.bot.save_guild_config(gid, conf)
        return web.HTTPFound(f'/guild/{gid}')

async def setup(bot):
    await bot.add_cog(WebAdmin(bot))