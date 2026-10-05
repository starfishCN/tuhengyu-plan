#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const file = process.env.SNOWLUMA_ONEBOT_CONFIG || '/app/data/config/onebot.json';
const url = process.env.ASTRBOT_WS_URL || 'ws://astrbot:6199/ws';
const token = process.env.ASTRBOT_WS_TOKEN || '';
const name = process.env.ASTRBOT_WS_NAME || 'tuhengyu-astrbot';

if (!/^wss?:\/\//.test(url)) throw new Error('ASTRBOT_WS_URL 必须以 ws:// 或 wss:// 开头');

function load() {
  if (!fs.existsSync(file)) return {};
  const value = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('配置根不是对象');
  return value;
}

const data = load();
if (!data.networks || typeof data.networks !== 'object' || Array.isArray(data.networks)) data.networks = {};
for (const key of ['httpServers', 'httpClients', 'wsServers', 'wsClients']) {
  if (data.networks[key] === undefined) data.networks[key] = [];
  if (!Array.isArray(data.networks[key])) throw new Error(`networks.${key} 不是数组`);
}
if (!data.statusCommand) data.statusCommand = { enabled: true, swallow: false, cooldownSeconds: 5, trigger: '#sl' };
if (!data.historySync) data.historySync = { enabled: false };
if (!data.notifications) data.notifications = { channelIds: [] };

const entry = {
  name,
  enabled: true,
  url,
  role: 'Universal',
  messageFormat: 'array',
  reportSelfMessage: false,
  reconnectIntervalMs: 5000,
};
if (token) entry.accessToken = token;
const index = data.networks.wsClients.findIndex(item => item && item.name === name);
if (index >= 0) data.networks.wsClients[index] = { ...data.networks.wsClients[index], ...entry };
else data.networks.wsClients.push(entry);

const dir = path.dirname(file);
fs.mkdirSync(dir, { recursive: true });
if (fs.existsSync(file)) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  fs.copyFileSync(file, `${file}.tuhengyu-${stamp}.bak`);
}
const temp = path.join(dir, `.${path.basename(file)}.${crypto.randomBytes(6).toString('hex')}.tmp`);
fs.writeFileSync(temp, `${JSON.stringify(data, null, 2)}\n`, { mode: 0o600 });
fs.renameSync(temp, file);
console.log(`已写入 SnowLuma OneBot WS 客户端：${name}`);
console.log(`目标：${url}`);