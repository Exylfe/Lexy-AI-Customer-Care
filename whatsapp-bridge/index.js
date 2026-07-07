/*
Lexy WhatsApp Bridge — Generic customer version
================================================
Run: node whatsapp-bridge/index.js
Requires: whatsapp_server.py running on port 5005
*/

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require("path");
require("dotenv").config();

// ─── CONFIG ─────────────────────────────────────────────────────
const BRAIN_URL = "http://localhost:5005/chat";
const BRAIN_SECRET = process.env.BRAIN_SECRET || "";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "admin123";

const DATA_DIR = path.join(__dirname, "..");
const CONTACTS_FILE = path.join(DATA_DIR, "contacts.json");
const MESSAGES_FILE = path.join(DATA_DIR, "messages.json");

// Admin mode state (per session)
let adminMode = false;
let adminSessionTimeout = null;

// ─── HELPERS ────────────────────────────────────────────────────

function normalizeNumber(num) {
  return num.replace(/[^0-9]/g, "").slice(-9);
}

function verifyAdmin(password) {
  return password === ADMIN_PASSWORD;
}

function readJSON(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch { return null; }
}

function writeJSON(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

// ─── CONTACTS ───────────────────────────────────────────────────

function getContactName(number) {
  const contacts = readJSON(CONTACTS_FILE);
  if (!contacts) return null;
  if (contacts[number]) return contacts[number];
  const norm = normalizeNumber(number);
  for (const [savedNum, name] of Object.entries(contacts)) {
    if (normalizeNumber(savedNum) === norm) return name;
  }
  return null;
}

function saveContact(number, name) {
  const contacts = readJSON(CONTACTS_FILE) || {};
  contacts[number] = name;
  writeJSON(CONTACTS_FILE, contacts);
}

// ─── MESSAGES ───────────────────────────────────────────────────

function loadMessages() {
  return readJSON(MESSAGES_FILE) || { messages: [] };
}

function saveIntentionalMessage(senderName, senderNumber, content) {
  const data = loadMessages();
  const newId = data.messages.length > 0
    ? Math.max(...data.messages.map(m => m.id)) + 1
    : 1;
  data.messages.push({
    id: newId,
    sender_name: senderName,
    sender_number: senderNumber,
    timestamp: new Date().toISOString(),
    content,
    status: "unread",
  });
  writeJSON(MESSAGES_FILE, data);
  return newId;
}

function getUnreadCount() {
  const data = loadMessages();
  return data.messages.filter(m => m.status === "unread").length;
}

function getMessagesOverview() {
  const data = loadMessages();
  const senders = {};
  for (const m of data.messages) {
    if (!senders[m.sender_name]) {
      senders[m.sender_name] = { name: m.sender_name, number: m.sender_number, total: 0, unread: 0 };
    }
    senders[m.sender_name].total++;
    if (m.status === "unread") senders[m.sender_name].unread++;
  }
  return senders;
}

function getMessagesFrom(name) {
  const data = loadMessages();
  const nameLower = name.toLowerCase();
  return data.messages.filter(m => m.sender_name.toLowerCase() === nameLower);
}

function markAllRead(name) {
  const data = loadMessages();
  const nameLower = name ? name.toLowerCase() : null;
  for (const m of data.messages) {
    if (!nameLower || m.sender_name.toLowerCase() === nameLower) {
      m.status = "read";
    }
  }
  writeJSON(MESSAGES_FILE, data);
}

// ─── MEMORY FILE ANALYSIS ──────────────────────────────────────

function searchMemoryFiles(query) {
  const memDir = DATA_DIR;
  const results = [];
  const files = fs.readdirSync(memDir).filter(f => f.startsWith("memory") && f.endsWith(".json"));
  for (const file of files) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(memDir, file), "utf8"));
      if (Array.isArray(data)) {
        for (const entry of data) {
          const content = (entry.content || "").toLowerCase();
          if (query instanceof RegExp ? query.test(content) : content.includes(query.toLowerCase())) {
            results.push(entry);
          }
        }
      }
    } catch {}
  }
  return results;
}

function getTopicAnalysis() {
  const topics = { weather: 0, business: 0, service: 0, tech: 0, general: 0 };
  const keywords = {
    weather: ["weather", "temperature", "rain", "sunny", "cloudy", "forecast"],
    business: ["business", "shop", "market", "sell", "buy", "entrepreneur", "startup"],
    service: ["service", "appointment", "booking", "schedule", "help", "support", "pricing"],
    tech: ["tech", "ai", "digital", "app", "website", "software", "developer"],
  };

  const memDir = DATA_DIR;
  const files = fs.readdirSync(memDir).filter(f => f.startsWith("memory") && f.endsWith(".json"));
  for (const file of files) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(memDir, file), "utf8"));
      if (Array.isArray(data)) {
        for (const entry of data) {
          const content = (entry.content || "").toLowerCase();
          for (const [topic, words] of Object.entries(keywords)) {
            if (words.some(w => content.includes(w))) {
              topics[topic]++;
            }
          }
        }
      }
    } catch {}
  }

  return Object.entries(topics)
    .sort((a, b) => b[1] - a[1])
    .reduce((acc, [k, v]) => { acc[k] = v; return acc; }, {});
}

// ─── INTENTIONAL MESSAGE DETECTION ─────────────────────────────

const LEAVE_MESSAGE_KEYWORDS = [
  "leave a message", "leave message", "message for the owner",
  "tell the owner", "give the owner a message", "i want to leave", "can i leave",
  "pass a message", "tell them that", "message for the business",
];

function isLeavingMessage(text) {
  const lower = text.toLowerCase();
  return LEAVE_MESSAGE_KEYWORDS.some(kw => lower.includes(kw));
}

// ─── ADMIN COMMANDS ─────────────────────────────────────────────

function parseAdminCommand(text) {
  const parts = text.trim().split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const args = parts.slice(1);
  return { cmd, args, fullText: text.trim() };
}

async function handleAdminCommand(sock, sender, senderNumber, command) {
  const { cmd, args, fullText } = command;

  // ── /exit — Leave admin mode ──
  if (cmd === "/exit" || cmd === "exit") {
    adminMode = false;
    clearTimeout(adminSessionTimeout);
    await sock.sendMessage(sender, { text: "Admin mode closed. Back to normal mode 👋" });
    return true;
  }

  // ── /messages — Overview of all messages ──
  if (cmd === "/messages") {
    const overview = getMessagesOverview();
    const names = Object.keys(overview);
    if (names.length === 0) {
      await sock.sendMessage(sender, { text: "📭 No messages yet." });
      return true;
    }
    const unread = getUnreadCount();
    let reply = `📬 *${unread} unread* — ${names.length} people:\n\n`;
    for (const [name, info] of Object.entries(overview)) {
      reply += `• *${info.name}* — ${info.total} msgs (${info.unread} unread)\n`;
    }
    reply += "\nReply with /read <name> to mark as read.";
    reply += "\nReply with /chat <name> to see their full conversation.";
    await sock.sendMessage(sender, { text: reply });
    return true;
  }

  // ── /read — Mark all read ──
  if (cmd === "/read") {
    const name = args.join(" ");
    if (name) {
      markAllRead(name);
      await sock.sendMessage(sender, { text: `✅ Messages from *${name}* marked as read.` });
    } else {
      markAllRead();
      await sock.sendMessage(sender, { text: "✅ All messages marked as read." });
    }
    return true;
  }

  // ── /chat — Show chat history with someone ──
  if (cmd === "/chat") {
    const name = args.join(" ");
    if (!name) {
      await sock.sendMessage(sender, { text: "Usage: /chat <name>" });
      return true;
    }
    const chats = searchMemoryFiles(name);
    if (chats.length === 0) {
      await sock.sendMessage(sender, { text: `No chat history found for *${name}*.` });
      return true;
    }
    let reply = `💬 *Chat history with ${name}* (${chats.length} messages):\n\n`;
    for (const entry of chats.slice(-10)) {
      const role = entry.role === "user" ? "👤" : "🤖";
      const content = (entry.content || "").substring(0, 300);
      reply += `${role} ${content}\n\n`;
    }
    await sock.sendMessage(sender, { text: reply.substring(0, 4000) });
    return true;
  }

  // ── /summary — Daily activity summary ──
  if (cmd === "/summary") {
    const data = loadMessages();
    const total = data.messages.length;
    const unique = new Set(data.messages.map(m => m.sender_name)).size;
    const unread = getUnreadCount();
    const topics = getTopicAnalysis();
    const topTopic = Object.keys(topics)[0] || "none";

    let reply = `📊 *Daily Summary*\n\n`;
    reply += `• Total messages: ${total}\n`;
    reply += `• Unique people: ${unique}\n`;
    reply += `• Unread: ${unread}\n`;
    reply += `• Top topic: ${topTopic}\n\n`;
    reply += `*Topic breakdown:*\n`;
    for (const [topic, count] of Object.entries(topics)) {
      const emojiMap = { weather: "🌤️", business: "💼", service: "🔧", tech: "💻", general: "💬" };
      reply += `${emojiMap[topic] || "•"} ${topic}: ${count}\n`;
    }
    await sock.sendMessage(sender, { text: reply });
    return true;
  }

  return false; // Not an admin command
}

// ─── BRAIN COMMUNICATION ───────────────────────────────────────

async function sendToBrain(senderNumber, messageText, senderName) {
  const https = require("https");
  return new Promise((resolve) => {
    const data = JSON.stringify({
      number: senderNumber,
      message: messageText,
      name: senderName,
      admin_mode: adminMode,
    });

    const urlObj = new URL(BRAIN_URL);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(data),
        ...(BRAIN_SECRET ? { "X-Brain-Secret": BRAIN_SECRET } : {}),
      },
    };

    const req = https.request(options, (res) => {
      let body = "";
      res.on("data", chunk => body += chunk);
      res.on("end", () => {
        try { resolve(JSON.parse(body).reply || ""); }
        catch { resolve(""); }
      });
    });
    req.on("error", () => resolve(""));
    req.write(data);
    req.end();
  });
}

// ─── MAIN ───────────────────────────────────────────────────────

async function startBot() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  const sock = makeWASocket({
    printQRInTerminal: true,
    auth: state,
    browser: ["Lexy (WhatsApp)", "", "1.0.0"],
    markOnlineOnConnect: true,
    syncFullHistory: false,
  });

  // Save QR to file for web dashboard
  sock.ev.on("qr", (qr) => {
    // qrcode-terminal is noisy — we also save to file for the dashboard
    try {
      qrcode.generate(qr, { small: true });
      // Save QR to file for web dashboard
      const fs = require("fs");
      const path = require("path");
      const qrPng = path.join(__dirname, "qr.txt");
      fs.writeFileSync(qrPng, qr);
      // Generate PNG via external tool? For now, save raw text
    } catch {}
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async ({ connection, lastDisconnect }) => {
    if (connection === "close") {
      const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
      console.log("Connection closed, reconnecting:", shouldReconnect);
      if (shouldReconnect) startBot();
    } else if (connection === "open") {
      console.log("✅ WhatsApp connected!");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const msg of messages) {
      if (msg.key.fromMe) continue;
      if (!msg.message?.conversation && !msg.message?.extendedTextMessage?.text) continue;

      const text = msg.message.conversation || msg.message.extendedTextMessage.text;
      const senderNumber = msg.key.remoteJid.replace(/[^0-9]/g, "");
      const sender = msg.key.remoteJid;
      const pushName = msg.pushName || "Unknown";

      // ── Admin mode entry via password ──
      if (!adminMode && verifyAdmin(text.trim())) {
        adminMode = true;
        clearTimeout(adminSessionTimeout);
        adminSessionTimeout = setTimeout(() => {
          adminMode = false;
          console.log("Admin session timed out");
        }, 30 * 60 * 1000); // 30 min timeout
        await sock.sendMessage(sender, {
          text: "🔐 *Admin mode activated*\n\nCommands:\n• `/messages` — view all messages\n• `/read <name>` — mark messages read\n• `/chat <name>` — view chat history\n• `/summary` — daily activity\n• `exit` — leave admin mode",
        });
        continue;
      }

      // ── Admin commands ──
      if (adminMode) {
        const command = parseAdminCommand(text);
        const handled = await handleAdminCommand(sock, sender, senderNumber, command);
        if (handled) continue;
      }

      // ── Intentional message detection ──
      if (isLeavingMessage(text)) {
        const name = pushName;
        saveIntentionalMessage(name, senderNumber, text);
        await sock.sendMessage(sender, {
          text: `📝 Got it! Your message has been saved and will be delivered to the owner.`,
        });
        continue;
      }

      // ── Normal chat — send to brain ──
      const contactName = getContactName(senderNumber) || pushName;
      const reply = await sendToBrain(senderNumber, text, contactName);
      if (reply) {
        await sock.sendMessage(sender, { text: reply });
      } else {
        await sock.sendMessage(sender, { text: "⚠️ Brain server is offline. Please check the dashboard." });
      }
    }
  });
}

startBot();
