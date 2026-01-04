async function postJson(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  const j = await r.json().catch(()=> ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(()=> el.classList.add("show"), 10);
  setTimeout(()=> {
    el.classList.remove("show");
    setTimeout(()=> el.remove(), 250);
  }, 1800);
}

function setSeg(hiddenId, value, btn) {
  document.getElementById(hiddenId).value = value;
  const parent = btn.parentElement;
  [...parent.querySelectorAll(".seg-btn")].forEach(b=> b.classList.remove("active"));
  btn.classList.add("active");
}

function parseCsv(s) {
  return (s || "")
    .split(",")
    .map(x => x.trim())
    .filter(x => x.length > 0);
}

function buildMultiSelect(containerId, roles, selectedIds) {
  const root = document.getElementById(containerId);
  root.innerHTML = "";

  const box = document.createElement("div");
  box.className = "multi-box";

  const chips = document.createElement("div");
  chips.className = "chips";

  const selectWrap = document.createElement("div");
  selectWrap.className = "select-wrap";

  const select = document.createElement("select");
  select.className = "select";
  const opt0 = document.createElement("option");
  opt0.value = "";
  opt0.textContent = "追加するロールを選択…";
  select.appendChild(opt0);

  roles.forEach(r => {
    const o = document.createElement("option");
    o.value = r.id;
    o.textContent = r.name;
    select.appendChild(o);
  });

  const chev = document.createElement("span");
  chev.className = "chev";
  chev.textContent = "▾";
  selectWrap.appendChild(select);
  selectWrap.appendChild(chev);

  function renderChips() {
    chips.innerHTML = "";
    selectedIds.forEach(id => {
      const role = roles.find(x => x.id === id);
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = role ? role.name : ("Role " + id);

      const x = document.createElement("button");
      x.className = "chip-x";
      x.type = "button";
      x.textContent = "×";
      x.onclick = () => {
        selectedIds = selectedIds.filter(v => v !== id);
        renderChips();
      };

      chip.appendChild(x);
      chips.appendChild(chip);
    });
  }

  select.onchange = () => {
    const v = select.value;
    if (v && !selectedIds.includes(v)) {
      selectedIds.push(v);
      renderChips();
    }
    select.value = "";
  };

  box.appendChild(chips);
  box.appendChild(selectWrap);
  root.appendChild(box);

  renderChips();

  return () => selectedIds; // getter
}

// Ticket Panel page bootstrap
(function initTicketPanelPage(){
  if (!window.__ROLES__ || !window.__PANEL__) return;

  // initial selection
  const staffSel = (window.__PANEL__.permissions && window.__PANEL__.permissions.staff_role_ids) || [];
  const viewSel  = (window.__PANEL__.permissions && window.__PANEL__.permissions.viewer_role_ids) || [];

  window.__getStaffRoles = buildMultiSelect("p_staff_roles", window.__ROLES__, staffSel.map(String));
  window.__getViewerRoles = buildMultiSelect("p_viewer_roles", window.__ROLES__, viewSel.map(String));
})();

function collectTicketPanelFromForm() {
  const panel = JSON.parse(JSON.stringify(window.__PANEL__ || {}));

  panel.panel_name = document.getElementById("p_panel_name").value.trim() || "panel";
  panel.enabled = document.getElementById("p_enabled").checked;

  panel.mode = document.getElementById("p_mode").value;
  panel.name_template = document.getElementById("p_name_template").value.trim() || "ticket-{count}-{user}";

  panel.parent_category_id = document.getElementById("p_parent_category_id").value;
  panel.thread_parent_channel_id = document.getElementById("p_thread_parent_channel_id").value;

  panel.types = parseCsv(document.getElementById("p_types").value);

  panel.limits = panel.limits || {};
  panel.limits.max_open_per_user = parseInt(document.getElementById("p_max_open").value || "5", 10);
  panel.limits.cooldown_minutes = parseInt(document.getElementById("p_cooldown").value || "30", 10);

  panel.permissions = panel.permissions || {};
  panel.permissions.staff_role_ids = (window.__getStaffRoles ? window.__getStaffRoles() : []).map(String);
  panel.permissions.viewer_role_ids = (window.__getViewerRoles ? window.__getViewerRoles() : []).map(String);

  panel.auto_delete = panel.auto_delete || {};
  panel.auto_delete.enabled = document.getElementById("p_inactive_enabled").checked;
  panel.auto_delete.inactive_minutes = parseInt(document.getElementById("p_inactive_minutes").value || "0", 10);

  panel.modal = panel.modal || {};
  panel.modal.enabled = document.getElementById("p_modal_enabled").checked;
  panel.modal.labels = panel.modal.labels || {};
  panel.modal.labels.type = document.getElementById("p_label_type").value || "ジャンル";
  panel.modal.labels.body = document.getElementById("p_label_body").value || "本文";
  panel.modal.labels.urgency = document.getElementById("p_label_urgency").value || "緊急度";
  panel.modal.labels.image = document.getElementById("p_label_image").value || "参考画像URL（任意）";

  panel.open_message = panel.open_message || {};
  panel.open_message.embed = panel.open_message.embed || {};
  panel.open_message.embed.description = document.getElementById("p_open_desc").value || "";

  panel.rules_embed = panel.rules_embed || {};
  panel.rules_embed.description = document.getElementById("p_rules_desc").value || "";

  panel.close = panel.close || {};
  panel.close.confirm_required = document.getElementById("p_close_confirm").checked;
  panel.close.closed_category_id = document.getElementById("p_closed_category_id").value;
  panel.close.allow_reopen = document.getElementById("p_allow_reopen").checked;
  panel.close.delete_after_days = parseInt(document.getElementById("p_delete_after_days").value || "14", 10);

  return panel;
}

async function ticketSavePanel(gid, panelIndex) {
  try {
    const panel = collectTicketPanelFromForm();
    await postJson(`/guild/${gid}/api/ticket/panel/update`, {
      panel_index: panelIndex,
      panel: panel
    });
    toast("保存しました");
    window.__PANEL__ = panel;
  } catch (e) {
    console.error(e);
    alert("保存に失敗: " + e.message);
  }
}

async function ticketDeployPanel(gid, panelIndex) {
  try {
    const depCh = prompt("設置先のチャンネルIDを入力（または空でキャンセル）");
    if (!depCh) return;
    await ticketSavePanel(gid, panelIndex);
    await postJson(`/guild/${gid}/api/ticket/panel/deploy`, {
      panel_index: panelIndex,
      channel_id: depCh
    });
    toast("Discordに設置しました");
  } catch (e) {
    console.error(e);
    alert("設置に失敗: " + e.message);
  }
}

async function ticketCreatePanel(gid) {
  try {
    const name = prompt("新しいパネル名");
    if (!name) return;
    const j = await postJson(`/guild/${gid}/api/ticket/panel/create`, {panel_name: name});
    toast("パネル追加しました");
    location.href = `/guild/${gid}/settings/ticket?panel=${j.index}`;
  } catch (e) {
    console.error(e);
    alert("追加に失敗: " + e.message);
  }
}

async function ticketDeletePanel(gid, panelIndex) {
  if (!confirm("このパネルを削除します。設置済みメッセージも削除します。よろしいですか？")) return;
  try {
    await postJson(`/guild/${gid}/api/ticket/panel/delete`, {panel_index: panelIndex});
    toast("削除しました");
    location.href = `/guild/${gid}/settings/ticket?panel=0`;
  } catch (e) {
    console.error(e);
    alert("削除に失敗: " + e.message);
  }
}
