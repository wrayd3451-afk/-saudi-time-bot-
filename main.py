/**
 * ===================================================================
 * بوت إدارة سيرفر رول بلاي (FiveM) - ملف واحد شامل
 * ===================================================================
 */

require('dotenv').config();
const {
  Client,
  GatewayIntentBits,
  Partials,
  REST,
  Routes,
  SlashCommandBuilder,
  PermissionFlagsBits,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  StringSelectMenuBuilder,
  ChannelType,
  AttachmentBuilder,
} = require('discord.js');
const Database = require('better-sqlite3');
const path = require('path');

// ===================================================================
// 1) الإعدادات العامة
// ===================================================================
const CONFIG = {
  token: process.env.DISCORD_TOKEN,
  clientId: process.env.CLIENT_ID,
  guildId: process.env.GUILD_ID,
  logChannelId: process.env.LOG_CHANNEL_ID || null,
  ticketLogChannelId: process.env.TICKET_LOG_CHANNEL_ID || null,
  adminRoleId: process.env.ADMIN_ROLE_ID || null,
  activeRoleId: process.env.ACTIVE_ROLE_ID || null,
  pointsPerRank: 100,
  vrp: {
    enabled: (process.env.VRP_ENABLED || 'false').toLowerCase() === 'true',
    host: process.env.VRP_DB_HOST || 'localhost',
    port: Number(process.env.VRP_DB_PORT || 3306),
    user: process.env.VRP_DB_USER || 'root',
    password: process.env.VRP_DB_PASSWORD || '',
    database: process.env.VRP_DB_NAME || '',
    table: process.env.VRP_TABLE_USERS || 'users',
    colIdentifier: process.env.VRP_COL_IDENTIFIER || 'identifier',
    colMoney: process.env.VRP_COL_MONEY || 'bank',
    colJob: process.env.VRP_COL_JOB || 'job',
  },
};

// ===================================================================
// 2) تعريف الوظائف والرتب
// ===================================================================
const JOBS = {
  military: { name: 'العسكرية', emoji: '👮', ranks: ['متطوع', 'جندي', 'عريف', 'رقيب', 'ملازم', 'نقيب', 'قائد'] },
  law: { name: 'القانون', emoji: '⚖️', ranks: ['متدرب', 'محامي', 'مستشار', 'قاضي مساعد', 'قاضي', 'رئيس المحكمة'] },
  crime: { name: 'الإجرام', emoji: '🔫', ranks: ['مبتدئ', 'عضو', 'موثوق', 'يد يمنى', 'زعيم'] },
  media: { name: 'الإعلام', emoji: '📺', ranks: ['متدرب', 'مراسل', 'محرر', 'رئيس تحرير'] },
  ems: { name: 'الإسعاف', emoji: '🚑', ranks: ['متدرب', 'مسعف', 'ممرض', 'طبيب', 'رئيس الأطباء'] },
  civil: { name: 'الوظائف المدنية', emoji: '🚕', ranks: ['موظف', 'موظف أول', 'مشرف'] },
};

function jobChoices() {
  return Object.entries(JOBS).map(([key, j]) => ({ name: `${j.emoji} ${j.name}`, value: key }));
}

// ===================================================================
// 3) قاعدة البيانات (SQLite)
// ===================================================================
const db = new Database(path.join(__dirname, 'data.sqlite'));
db.pragma('journal_mode = WAL');

db.exec(`
CREATE TABLE IF NOT EXISTS players (
  discord_id   TEXT PRIMARY KEY,
  player_id    TEXT,
  active       INTEGER DEFAULT 0,
  job          TEXT,
  rank_index   INTEGER DEFAULT 0,
  points       INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS records (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  discord_id   TEXT,
  type         TEXT,
  detail       TEXT,
  moderator_id TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reservations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  type         TEXT,
  details      TEXT,
  requested_by TEXT,
  status       TEXT DEFAULT 'pending',
  confirmed_by TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id   TEXT UNIQUE,
  user_id      TEXT,
  department   TEXT,
  status       TEXT DEFAULT 'open',
  claimed_by   TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  closed_at    TEXT
);

CREATE TABLE IF NOT EXISTS ticket_config (
  guild_id     TEXT PRIMARY KEY,
  category_id  TEXT
);
`);

function getPlayer(discordId) {
  let row = db.prepare('SELECT * FROM players WHERE discord_id = ?').get(discordId);
  if (!row) {
    db.prepare('INSERT INTO players (discord_id) VALUES (?)').run(discordId);
    row = db.prepare('SELECT * FROM players WHERE discord_id = ?').get(discordId);
  }
  return row;
}

function updatePlayer(discordId, fields) {
  getPlayer(discordId);
  const keys = Object.keys(fields);
  if (keys.length === 0) return;
  const setClause = keys.map((k) => `${k} = ?`).join(', ');
  const values = keys.map((k) => fields[k]);
  db.prepare(`UPDATE players SET ${setClause}, updated_at = CURRENT_TIMESTAMP WHERE discord_id = ?`).run(...values, discordId);
}

function addRecord(discordId, type, detail, moderatorId) {
  db.prepare('INSERT INTO records (discord_id, type, detail, moderator_id) VALUES (?, ?, ?, ?)').run(discordId, type, detail || '', moderatorId || null);
}

// ===================================================================
// 4) ربط VRP (اختياري)
// ===================================================================
let mysqlPool = null;
if (CONFIG.vrp.enabled) {
  const mysql = require('mysql2/promise');
  mysqlPool = mysql.createPool({
    host: CONFIG.vrp.host,
    port: CONFIG.vrp.port,
    user: CONFIG.vrp.user,
    password: CONFIG.vrp.password,
    database: CONFIG.vrp.database,
    waitForConnections: true,
    connectionLimit: 5,
  });
  console.log('[VRP] الاتصال بقاعدة بيانات السيرفر مُفعّل.');
}

async function getVrpPlayerData(identifier) {
  if (!mysqlPool) return null;
  try {
    const [rows] = await mysqlPool.query(
      `SELECT ${CONFIG.vrp.colIdentifier} AS identifier, ${CONFIG.vrp.colMoney} AS money, ${CONFIG.vrp.colJob} AS job
       FROM ${CONFIG.vrp.table} WHERE ${CONFIG.vrp.colIdentifier} = ? LIMIT 1`,
      [identifier]
    );
    return rows[0] || null;
  } catch (err) {
    console.error('[VRP] خطأ في الاستعلام:', err.message);
    return null;
  }
}

// ===================================================================
// 5) إعداد عميل الديسكورد
// ===================================================================
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
  partials: [Partials.Channel],
});

function isAdmin(interaction) {
  if (interaction.member.permissions.has(PermissionFlagsBits.Administrator)) return true;
  if (CONFIG.adminRoleId && interaction.member.roles.cache.has(CONFIG.adminRoleId)) return true;
  return false;
}

async function denyNotAdmin(interaction) {
  await interaction.reply({ content: '❌ ما عندك صلاحية استخدام هذا الأمر.', ephemeral: true });
}

async function sendLog(embed) {
  if (!CONFIG.logChannelId) return;
  try {
    const channel = await client.channels.fetch(CONFIG.logChannelId);
    if (channel) await channel.send({ embeds: [embed] });
  } catch (err) {
    console.error('[Log] تعذر إرسال اللوق:', err.message);
  }
}

function baseEmbed(title, color = 0x2b6cff) {
  return new EmbedBuilder().setTitle(title).setColor(color).setTimestamp();
}

// ===================================================================
// 6) تعريف أوامر Slash
// ===================================================================
const commands = [
  new SlashCommandBuilder().setName('تفعيل').setDescription('تفعيل عضوية لاعب في السيرفر').addUserOption((o) => o.setName('العضو').setDescription('العضو المطلوب تفعيله').setRequired(true)),
  new SlashCommandBuilder().setName('استدعاء').setDescription('استدعاء عضو من قبل الإدارة').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)).addStringOption((o) => o.setName('السبب').setDescription('سبب الاستدعاء').setRequired(true)),
  new SlashCommandBuilder().setName('رتب').setDescription('تعديل رتبة اللاعب داخل وظيفته الحالية').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)).addIntegerOption((o) => o.setName('الرتبة').setDescription('رقم الرتبة').setRequired(true).setMinValue(0)),
  new SlashCommandBuilder().setName('اسماء').setDescription('عرض قائمة اللاعبين المسجلين'),
  new SlashCommandBuilder().setName('توظيف').setDescription('توظيف عضو في إحدى الوظائف').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)).addStringOption((o) => o.setName('الوظيفة').setDescription('الوظيفة').setRequired(true).addChoices(...jobChoices())),
  new SlashCommandBuilder().setName('تقاعد').setDescription('إنهاء خدمة اللاعب (تقاعد)').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)),
  new SlashCommandBuilder().setName('استقالة').setDescription('تقديم استقالة عضو من وظيفته').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)),
  new SlashCommandBuilder().setName('إخلاء').setDescription('إخلاء طرف / فصل عضو من وظيفته').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)).addStringOption((o) => o.setName('السبب').setDescription('السبب').setRequired(true)),
  new SlashCommandBuilder().setName('حجز').setDescription('تقديم طلب حجز').addStringOption((o) => o.setName('النوع').setDescription('النوع').setRequired(true)).addStringOption((o) => o.setName('التفاصيل').setDescription('التفاصيل').setRequired(true)),
  new SlashCommandBuilder().setName('تأكيد').setDescription('تأكيد طلب حجز عبر رقمه').addIntegerOption((o) => o.setName('رقم_الطلب').setDescription('رقم الطلب').setRequired(true)),
  new SlashCommandBuilder().setName('ربط').setDescription('ربط حسابك برقم هويتك').addStringOption((o) => o.setName('رقم_اللاعب').setDescription('identifier').setRequired(true)),
  new SlashCommandBuilder().setName('بطاقة').setDescription('عرض بطاقة بيانات لاعب').addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(false)),
  new SlashCommandBuilder().setName('نقاط').setDescription('إضافة أو خصم نقاط من عضو').addStringOption((o) => o.setName('العملية').setDescription('إضافة أو خصم').setRequired(true).addChoices({ name: 'إضافة', value: 'add' }, { name: 'خصم', value: 'sub' })).addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)).addIntegerOption((o) => o.setName('العدد').setDescription('العدد').setRequired(true).setMinValue(1)).addStringOption((o) => o.setName('السبب').setDescription('السبب').setRequired(false)),
  new SlashCommandBuilder().setName('تذاكر_اعداد').setDescription('نشر لوحة فتح التذاكر').addChannelOption((o) => o.setName('التصنيف').setDescription('التصنيف').addChannelTypes(ChannelType.GuildCategory).setRequired(false)),
].map((c) => c.toJSON());

// ===================================================================
// 7) تسجيل الأوامر والتشغيل
// ===================================================================
client.once('ready', async () => {
  console.log(`✅ تم تسجيل الدخول باسم ${client.user.tag}`);
  try {
    const rest = new REST({ version: '10' }).setToken(CONFIG.token);
    await rest.put(Routes.applicationGuildCommands(CONFIG.clientId, CONFIG.guildId), { body: commands });
    console.log('✅ تم تسجيل جميع الأوامر بنجاح.');
  } catch (err) {
    console.error('❌ فشل تسجيل الأوامر:', err);
  }
});

client.on('interactionCreate', async (interaction) => {
  try {
    if (interaction.isChatInputCommand()) {
      await handleSlashCommand(interaction);
    } else if (interaction.isStringSelectMenu()) {
      await handleSelectMenu(interaction);
    } else if (interaction.isButton()) {
      await handleButton(interaction);
    }
  } catch (err) {
    console.error('خطأ:', err);
    const payload = { content: '⚠️ حدث خطأ أثناء تنفيذ الأمر.', ephemeral: true };
    if (interaction.deferred || interaction.replied) {
      await interaction.followUp(payload).catch(() => {});
    } else {
      await interaction.reply(payload).catch(() => {});
    }
  }
});

async function handleSlashCommand(interaction) {
  const { commandName } = interaction;

  if (commandName === 'تفعيل') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    updatePlayer(member.id, { active: 1 });
    addRecord(member.id, 'activate', 'تم تفعيل العضوية', interaction.user.id);
    if (CONFIG.activeRoleId) {
      const gm = await interaction.guild.members.fetch(member.id).catch(() => null);
      if (gm) await gm.roles.add(CONFIG.activeRoleId).catch(() => {});
    }
    const embed = baseEmbed('✅ تفعيل عضوية', 0x2ecc71).setDescription(`تم تفعيل عضوية ${member} بواسطة ${interaction.user}`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'استدعاء') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const reason = interaction.options.getString('السبب');
    addRecord(member.id, 'summon', reason, interaction.user.id);
    const embed = baseEmbed('📢 استدعاء إداري', 0xf39c12).setDescription(`تم استدعاء ${member}`).addFields({ name: 'السبب', value: reason });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'رتب') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const rankIndex = interaction.options.getInteger('الرتبة');
    const player = getPlayer(member.id);
    if (!player.job || !JOBS[player.job]) return interaction.reply({ content: '❌ العضو غير موظف.', ephemeral: true });
    const job = JOBS[player.job];
    if (rankIndex >= job.ranks.length) return interaction.reply({ content: '❌ الرتبة غير موجودة.', ephemeral: true });
    updatePlayer(member.id, { rank_index: rankIndex });
    addRecord(member.id, 'rank_change', `${job.name} -> ${job.ranks[rankIndex]}`, interaction.user.id);
    const embed = baseEmbed('🎖️ تعديل رتبة', 0x3498db).setDescription(`تم تعديل رتبة ${member} إلى **${job.ranks[rankIndex]}**`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'اسماء') {
    const rows = db.prepare('SELECT * FROM players WHERE job IS NOT NULL ORDER BY job, rank_index DESC').all();
    if (rows.length === 0) return interaction.reply({ content: 'لا يوجد موظفون.', ephemeral: true });
    const grouped = {};
    for (const r of rows) { grouped[r.job] = grouped[r.job] || []; grouped[r.job].push(r); }
    const embed = baseEmbed('📋 قائمة الموظفين');
    for (const [jobKey, list] of Object.entries(grouped)) {
      const job = JOBS[jobKey];
      if (!job) continue;
      const lines = list.map((r) => `<@${r.discord_id}> — ${job.ranks[r.rank_index] || '-'} (${r.points} نقطة)`);
      embed.addFields({ name: `${job.emoji} ${job.name}`, value: lines.join('\n').slice(0, 1024) });
    }
    await interaction.reply({ embeds: [embed] });
  }
  else if (commandName === 'توظيف') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const jobKey = interaction.options.getString('الوظيفة');
    const job = JOBS[jobKey];
    updatePlayer(member.id, { job: jobKey, rank_index: 0, active: 1 });
    addRecord(member.id, 'hire', `تم توظيفه في ${job.name}`, interaction.user.id);
    const embed = baseEmbed('🧑‍💼 توظيف جديد', 0x2ecc71).setDescription(`تم توظيف ${member} في **${job.name}**`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'تقاعد') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    updatePlayer(member.id, { job: null, rank_index: 0 });
    addRecord(member.id, 'retire', 'تقاعد', interaction.user.id);
    const embed = baseEmbed('🏅 تقاعد', 0x9b59b6).setDescription(`تم تقاعد ${member}`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'استقالة') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    updatePlayer(member.id, { job: null, rank_index: 0 });
    addRecord(member.id, 'resign', 'استقالة', interaction.user.id);
    const embed = baseEmbed('📄 استقالة', 0xe67e22).setDescription(`استقالة ${member}`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'إخلاء') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const reason = interaction.options.getString('السبب');
    updatePlayer(member.id, { job: null, rank_index: 0 });
    addRecord(member.id, 'fire', reason, interaction.user.id);
    const embed = baseEmbed('⛔ إخلاء طرف', 0xe74c3c).setDescription(`إخلاء طرف ${member}`).addFields({ name: 'السبب', value: reason });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'حجز') {
    const type = interaction.options.getString('النوع');
    const details = interaction.options.getString('التفاصيل');
    const info = db.prepare('INSERT INTO reservations (type, details, requested_by) VALUES (?, ?, ?)').run(type, details, interaction.user.id);
    const embed = baseEmbed('📌 طلب حجز جديد', 0xf1c40f).setDescription(`رقم الطلب: **#${info.lastInsertRowid}**`).addFields({ name: 'النوع', value: type }, { name: 'التفاصيل', value: details });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'تأكيد') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const id = interaction.options.getInteger('رقم_الطلب');
    db.prepare("UPDATE reservations SET status = 'confirmed', confirmed_by = ? WHERE id = ?").run(interaction.user.id, id);
    const embed = baseEmbed('✅ تأكيد حجز', 0x2ecc71).setDescription(`تم تأكيد الطلب **#${id}**`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }
  else if (commandName === 'ربط') {
    const playerId = interaction.options.getString('رقم_اللاعب');
    updatePlayer(interaction.user.id, { player_id: playerId });
    await interaction.reply({ content: `✅ تم ربط حسابك بهوية اللاعب: **${playerId}**`, ephemeral: true });
  }
  else if (commandName === 'بطاقة') {
    const target = interaction.options.getUser('العضو') || interaction.user;
    const player = getPlayer(target.id);
    const job = JOBS[player.job];
    const embed = baseEmbed(`🪪 بطاقة ${target.username}`).setThumbnail(target.displayAvatarURL())
      .addFields(
        { name: 'رقم اللاعب', value: player.player_id || 'غير مربوط', inline: true },
        { name: 'الحالة', value: player.active ? '🟢 مفعّل' : '🔴 غير مفعّل', inline: true },
        { name: 'النقاط', value: String(player.points), inline: true },
        { name: 'الوظيفة', value: job ? `${job.emoji} ${job.name}` : 'بدون', inline: true },
        { name: 'الرتبة', value: job ? job.ranks[player.rank_index] || '-' : '-', inline: true }
      );
    if (CONFIG.vrp.enabled && player.player_id) {
      const vrpData = await getVrpPlayerData(player.player_id);
      if (vrpData) embed.addFields({ name: '💰 الرصيد', value: String(vrpData.money ?? '0'), inline: true });
    }
    await interaction.reply({ embeds: [embed] });
  }
  else if (commandName === 'نقاط') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const op = interaction.options.getString('العملية');
    const member = interaction.options.getUser('العضو');
    const amount = interaction.options.getInteger('العدد');
    const player = getPlayer(member.id);
    const newPoints = op === 'add' ? player.points + amount : Math.max(0, player.points - amount);
    updatePlayer(member.id, { points: newPoints });
    const embed = baseEmbed(op === 'add' ? '➕ إضافة نقاط' : '➖ خصم نقاط', op === 'add' ? 0x2ecc71 : 0xe74c3c).setDescription(`رصيد جديد: **${newPoints}**`);
    await interaction.reply({ embeds: [embed] });
  }
  else if (commandName === 'تذاكر_اعداد') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const menu = new StringSelectMenuBuilder().setCustomId('ticket_open_select').setPlaceholder('اختر القسم لفتح تذكرة').addOptions(
      { label: 'الدعم الفني', value: 'support', emoji: '🛠️' },
      { label: 'شكاوى', value: 'complaints', emoji: '📢' }
    );
    await interaction.reply({ embeds: [embed = baseEmbed('🎫 التذاكر')], components: [new ActionRowBuilder().addComponents(menu)] });
  }
}

const DEPARTMENTS = { support: '🛠️ الدعم الفني', complaints: '📢 شكاوى' };

async function handleSelectMenu(interaction) {
  if (interaction.customId === 'ticket_open_select') {
    await interaction.deferReply({ ephemeral: true });
    const dept = interaction.values[0];
    const channel = await interaction.guild.channels.create({
      name: `ticket-${interaction.user.username}`.toLowerCase().slice(0, 90),
      type: ChannelType.GuildText,
      permissionOverwrites: [
        { id: interaction.guild.roles.everyone.id, deny: [PermissionFlagsBits.ViewChannel] },
        { id: interaction.user.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] },
      ],
    });
    db.prepare('INSERT INTO tickets (channel_id, user_id, department) VALUES (?, ?, ?)').run(channel.id, interaction.user.id, dept);
    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('ticket_close').setLabel('إغلاق').setStyle(ButtonStyle.Danger)
    );
    await channel.send({ content: `${interaction.user}`, embeds: [baseEmbed('🎫 تذكرة جديدة')], components: [row] });
    await interaction.editReply({ content: `✅ تم فتح تذكرتك: ${channel}` });
  }
}

async function handleButton(interaction) {
  if (interaction.customId === 'ticket_close') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    await interaction.reply('🔒 يتم إغلاق التذكرة...');
    setTimeout(() => interaction.channel.delete().catch(() => {}), 3000);
  }
}

client.login(CONFIG.token);
