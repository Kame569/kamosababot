async function saveSettings(guildId) {
    const data = {
        lang: "ja",
        jl: {
            enabled: true,
            channel_join: document.getElementById('channel_join').value,
            channel_leave: document.getElementById('channel_leave').value,
            join_embed: {
                title: document.getElementById('j_title').value,
                description: document.getElementById('j_desc').value,
                color: 5763719
            },
            leave_embed: {
                title: "Goodbye",
                description: document.getElementById('l_desc').value,
                color: 15548997
            }
        },
        ticket: { panels: [], staff_roles: [] }, // 本来はフォームから取得
        rank: { enabled: true, types: ["chat"], cooldown: 60, formula: "level * 100" }
    };

    const res = await fetch(`/guild/${guildId}/api/save`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });

    if (res.ok) alert("設定を保存しました。");
}