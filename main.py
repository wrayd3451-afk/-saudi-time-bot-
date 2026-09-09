/**
 * ===================================================================
 *  بوت إدارة سيرفر رول بلاي (FiveM) - ملف واحد شامل
 * ===================================================================
 *  يحتوي:
 *   - إدارة السيرفر: تفعيل / استدعاء / رتب / اسماء / توظيف / تقاعد /
 *                     استقالة / إخلاء / حجز / تأكيد
 *   - نظام الوظائف الست + رتب وصلاحيات
 *   - نظام اللاعبين (ربط ديسكورد بهوية اللاعب، حالة، نقاط، سجل، عقوبات)
 *   - نظام التذاكر الكامل (فتح/استلام/تحويل/إغلاق/Transcript/Logs)
 *   - نظام النقاط (إضافة/خصم/سجل/ترقيات)
 *   - نظام VRP (قراءة اختيارية من قاعدة بيانات السيرفر عبر MySQL)
 *
 *  التشغيل:
 *   1) npm install
 *   2) انسخ .env.example إلى .env واملأ القيم
 *   3) node index.js
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
  // نقاط مطلوبة للترقية للرتبة التالية داخل نفس الوظيفة (عدّلها كما تحب)
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
// 3) قاعدة البيانات (SQLite - ملف واحد: data.sqlite)
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
  type         TEXT,     -- hire, fire, resign, retire, points_add, points_sub, penalty, note, activate
  detail       TEXT,
  moderator_id TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reservations (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  type         TEXT,
  details      TEXT,
  requested_by TEXT,
  status       TEXT DEFAULT 'pending', -- pending, confirmed, rejected
  confirmed_by TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id   TEXT UNIQUE,
  user_id      TEXT,
  department   TEXT,
  status       TEXT DEFAULT 'open', -- open, claimed, closed
  claimed_by   TEXT,
  created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
  closed_at    TEXT
);

CREATE TABLE IF NOT EXISTS ticket_config (
  guild_id     TEXT PRIMARY KEY,
  category_id  TEXT
);
`);

// دوال مساعدة لقاعدة البيانات
function getPlayer(discordId) {
  let row = db.prepare('SELECT * FROM players WHERE discord_id = ?').get(discordId);
  if (!row) {
    db.prepare('INSERT INTO players (discord_id) VALUES (?)').run(discordId);
    row = db.prepare('SELECT * FROM players WHERE discord_id = ?').get(discordId);
  }
  return row;
}

function updatePlayer(discordId, fields) {
  getPlayer(discordId); // تضمن وجود الصف
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
// 4) ربط اختياري بقاعدة بيانات VRP (MySQL) - لقراءة بيانات اللاعب من السيرفر
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

/**
 * يجلب بيانات اللاعب من قاعدة بيانات السيرفر (VRP/ESX/QBCore) عبر identifier.
 * ⚠️ عدّل اسم الجدول والأعمدة في .env حسب مخطط قاعدة بياناتك الفعلي،
 * لأن أسماء الجداول تختلف بين vRP وESX وQBCore.
 */
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
  // ---------- إدارة السيرفر ----------
  new SlashCommandBuilder()
    .setName('تفعيل')
    .setDescription('تفعيل عضوية لاعب في السيرفر')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو المطلوب تفعيله').setRequired(true)),

  new SlashCommandBuilder()
    .setName('استدعاء')
    .setDescription('استدعاء عضو من قبل الإدارة')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو المطلوب استدعاؤه').setRequired(true))
    .addStringOption((o) => o.setName('السبب').setDescription('سبب الاستدعاء').setRequired(true)),

  new SlashCommandBuilder()
    .setName('رتب')
    .setDescription('تعديل رتبة اللاعب داخل وظيفته الحالية')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true))
    .addIntegerOption((o) => o.setName('الرتبة').setDescription('رقم الرتبة (0 = الأدنى)').setRequired(true).setMinValue(0)),

  new SlashCommandBuilder()
    .setName('اسماء')
    .setDescription('عرض قائمة اللاعبين المسجلين'),

  new SlashCommandBuilder()
    .setName('توظيف')
    .setDescription('توظيف عضو في إحدى الوظائف')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true))
    .addStringOption((o) => o.setName('الوظيفة').setDescription('الوظيفة').setRequired(true).addChoices(...jobChoices())),

  new SlashCommandBuilder()
    .setName('تقاعد')
    .setDescription('إنهاء خدمة اللاعب (تقاعد)')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)),

  new SlashCommandBuilder()
    .setName('استقالة')
    .setDescription('تقديم استقالة عضو من وظيفته')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true)),

  new SlashCommandBuilder()
    .setName('إخلاء')
    .setDescription('إخلاء طرف / فصل عضو من وظيفته')
    .addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true))
    .addStringOption((o) => o.setName('السبب').setDescription('سبب الإخلاء').setRequired(true)),

  new SlashCommandBuilder()
    .setName('حجز')
    .setDescription('تقديم طلب حجز (اسم/رقم/موعد..)')
    .addStringOption((o) => o.setName('النوع').setDescription('نوع الحجز').setRequired(true))
    .addStringOption((o) => o.setName('التفاصيل').setDescription('تفاصيل الحجز').setRequired(true)),

  new SlashCommandBuilder()
    .setName('تأكيد')
    .setDescription('تأكيد طلب حجز عبر رقمه')
    .addIntegerOption((o) => o.setName('رقم_الطلب').setDescription('رقم طلب الحجز').setRequired(true)),

  // ---------- نظام اللاعبين ----------
  new SlashCommandBuilder()
    .setName('ربط')
    .setDescription('ربط حسابك في الديسكورد برقم هويتك داخل السيرفر')
    .addStringOption((o) => o.setName('رقم_اللاعب').setDescription('معرف/هوية اللاعب (identifier)').setRequired(true)),

  new SlashCommandBuilder()
    .setName('بطاقة')
    .setDescription('عرض بطاقة بيانات لاعب (الوظيفة، الرتبة، النقاط، السجل)')
    .addUserOption((o) => o.setName('العضو').setDescription('اتركه فارغًا لعرض بطاقتك').setRequired(false)),

  // ---------- نظام النقاط ----------
  new SlashCommandBuilder()
    .setName('نقاط')
    .setDescription('إضافة أو خصم نقاط من عضو')
    .addStringOption((o) =>
      o.setName('العملية').setDescription('إضافة أو خصم').setRequired(true).addChoices({ name: 'إضافة', value: 'add' }, { name: 'خصم', value: 'sub' })
    )
    .addUserOption((o) => o.setName('العضو').setDescription('العضو').setRequired(true))
    .addIntegerOption((o) => o.setName('العدد').setDescription('عدد النقاط').setRequired(true).setMinValue(1))
    .addStringOption((o) => o.setName('السبب').setDescription('سبب إضافة/خصم النقاط').setRequired(false)),

  // ---------- نظام التذاكر ----------
  new SlashCommandBuilder()
    .setName('تذاكر_اعداد')
    .setDescription('نشر لوحة فتح التذاكر في هذه القناة (للإدارة فقط)')
    .addChannelOption((o) => o.setName('التصنيف').setDescription('تصنيف (Category) إنشاء التذاكر بداخله').addChannelTypes(ChannelType.GuildCategory).setRequired(false)),
].map((c) => c.toJSON());

// ===================================================================
// 7) تسجيل الأوامر عند الإقلاع
// ===================================================================
client.once('ready', async () => {
  console.log(`✅ تم تسجيل الدخول باسم ${client.user.tag}`);
  try {
    const rest = new REST({ version: '10' }).setToken(CONFIG.token);
    await rest.put(Routes.applicationGuildCommands(CONFIG.clientId, CONFIG.guildId), { body: commands });
    console.log('✅ تم تسجيل جميع الأوامر بنجاح على السيرفر.');
  } catch (err) {
    console.error('❌ فشل تسجيل الأوامر:', err);
  }
});

// ===================================================================
// 8) معالجة تفاعلات الأوامر (Slash Commands)
// ===================================================================
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
    console.error('خطأ أثناء معالجة التفاعل:', err);
    const payload = { content: '⚠️ حدث خطأ غير متوقع أثناء تنفيذ الأمر.', ephemeral: true };
    if (interaction.deferred || interaction.replied) {
      await interaction.followUp(payload).catch(() => {});
    } else {
      await interaction.reply(payload).catch(() => {});
    }
  }
});

async function handleSlashCommand(interaction) {
  const { commandName } = interaction;

  // ------------------- /تفعيل -------------------
  if (commandName === 'تفعيل') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    updatePlayer(member.id, { active: 1 });
    addRecord(member.id, 'activate', 'تم تفعيل العضوية', interaction.user.id);
    if (CONFIG.activeRoleId) {
      const guildMember = await interaction.guild.members.fetch(member.id).catch(() => null);
      if (guildMember) await guildMember.roles.add(CONFIG.activeRoleId).catch(() => {});
    }
    const embed = baseEmbed('✅ تفعيل عضوية', 0x2ecc71)
      .setDescription(`تم تفعيل عضوية ${member} بواسطة ${interaction.user}`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }

  // ------------------- /استدعاء -------------------
  else if (commandName === 'استدعاء') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const reason = interaction.options.getString('السبب');
    addRecord(member.id, 'summon', reason, interaction.user.id);
    const embed = baseEmbed('📢 استدعاء إداري', 0xf39c12)
      .setDescription(`تم استدعاء ${member} بواسطة ${interaction.user}`)
      .addFields({ name: 'السبب', value: reason });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
    await member.send({ embeds: [baseEmbed('📢 تم استدعاؤك من قبل الإدارة', 0xf39c12).addFields({ name: 'السبب', value: reason })] }).catch(() => {});
  }

  // ------------------- /رتب -------------------
  else if (commandName === 'رتب') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const rankIndex = interaction.options.getInteger('الرتبة');
    const player = getPlayer(member.id);
    if (!player.job || !JOBS[player.job]) {
      return interaction.reply({ content: '❌ هذا العضو غير موظف حاليًا في أي وظيفة.', ephemeral: true });
    }
    const job = JOBS[player.job];
    if (rankIndex >= job.ranks.length) {
      return interaction.reply({ content: `❌ أعلى رتبة متاحة في وظيفة ${job.name} هي رقم ${job.ranks.length - 1}.`, ephemeral: true });
    }
    updatePlayer(member.id, { rank_index: rankIndex });
    addRecord(member.id, 'rank_change', `${job.name} -> ${job.ranks[rankIndex]}`, interaction.user.id);
    const embed = baseEmbed('🎖️ تعديل رتبة', 0x3498db)
      .setDescription(`تم تعديل رتبة ${member} إلى **${job.ranks[rankIndex]}** في وظيفة ${job.emoji} ${job.name}`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }

  // ------------------- /اسماء -------------------
  else if (commandName === 'اسماء') {
    const rows = db.prepare('SELECT * FROM players WHERE job IS NOT NULL ORDER BY job, rank_index DESC').all();
    if (rows.length === 0) {
      return interaction.reply({ content: 'لا يوجد لاعبون مسجلون في أي وظيفة حاليًا.', ephemeral: true });
    }
    const grouped = {};
    for (const r of rows) {
      grouped[r.job] = grouped[r.job] || [];
      grouped[r.job].push(r);
    }
    const embed = baseEmbed('📋 قائمة الموظفين المسجلين');
    for (const [jobKey, list] of Object.entries(grouped)) {
      const job = JOBS[jobKey];
      if (!job) continue;
      const lines = list.map((r) => `<@${r.discord_id}> — ${job.ranks[r.rank_index] || 'غير محدد'} (${r.points} نقطة)`);
      embed.addFields({ name: `${job.emoji} ${job.name}`, value: lines.join('\n').slice(0, 1024) });
    }
    await interaction.reply({ embeds: [embed] });
  }

  // ------------------- /توظيف -------------------
  else if (commandName === 'توظيف') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const jobKey = interaction.options.getString('الوظيفة');
    const job = JOBS[jobKey];
    updatePlayer(member.id, { job: jobKey, rank_index: 0, active: 1 });
    addRecord(member.id, 'hire', `تم توظيفه في ${job.name}`, interaction.user.id);
    const embed = baseEmbed('🧑‍💼 توظيف جديد', 0x2ecc71)
      .setDescription(`تم توظيف ${member} في وظيفة ${job.emoji} **${job.name}** برتبة **${job.ranks[0]}**`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
    await member.send({ embeds: [embed] }).catch(() => {});
  }

  // ------------------- /تقاعد -------------------
  else if (commandName === 'تقاعد') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const player = getPlayer(member.id);
    const jobName = JOBS[player.job]?.name || 'غير محدد';
    updatePlayer(member.id, { job: null, rank_index: 0 });
    addRecord(member.id, 'retire', `تقاعد من وظيفة ${jobName}`, interaction.user.id);
    const embed = baseEmbed('🏅 تقاعد', 0x9b59b6).setDescription(`تم تسجيل تقاعد ${member} من وظيفة **${jobName}**`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }

  // ------------------- /استقالة -------------------
  else if (commandName === 'استقالة') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const player = getPlayer(member.id);
    const jobName = JOBS[player.job]?.name || 'غير محدد';
    updatePlayer(member.id, { job: null, rank_index: 0 });
    addRecord(member.id, 'resign', `استقالة من وظيفة ${jobName}`, interaction.user.id);
    const embed = baseEmbed('📄 استقالة', 0xe67e22).setDescription(`تم تسجيل استقالة ${member} من وظيفة **${jobName}**`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }

  // ------------------- /إخلاء -------------------
  else if (commandName === 'إخلاء') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const member = interaction.options.getUser('العضو');
    const reason = interaction.options.getString('السبب');
    const player = getPlayer(member.id);
    const jobName = JOBS[player.job]?.name || 'غير محدد';
    updatePlayer(member.id, { job: null, rank_index: 0 });
    addRecord(member.id, 'fire', `إخلاء طرف من وظيفة ${jobName} - السبب: ${reason}`, interaction.user.id);
    const embed = baseEmbed('⛔ إخلاء طرف', 0xe74c3c)
      .setDescription(`تم إخلاء طرف ${member} من وظيفة **${jobName}**`)
      .addFields({ name: 'السبب', value: reason });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
    await member.send({ embeds: [embed] }).catch(() => {});
  }

  // ------------------- /حجز -------------------
  else if (commandName === 'حجز') {
    const type = interaction.options.getString('النوع');
    const details = interaction.options.getString('التفاصيل');
    const info = db.prepare('INSERT INTO reservations (type, details, requested_by) VALUES (?, ?, ?)').run(type, details, interaction.user.id);
    const embed = baseEmbed('📌 طلب حجز جديد', 0xf1c40f)
      .setDescription(`رقم الطلب: **#${info.lastInsertRowid}**`)
      .addFields({ name: 'النوع', value: type }, { name: 'التفاصيل', value: details }, { name: 'مقدّم الطلب', value: `${interaction.user}` });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
  }

  // ------------------- /تأكيد -------------------
  else if (commandName === 'تأكيد') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const id = interaction.options.getInteger('رقم_الطلب');
    const reservation = db.prepare('SELECT * FROM reservations WHERE id = ?').get(id);
    if (!reservation) return interaction.reply({ content: '❌ لا يوجد طلب حجز بهذا الرقم.', ephemeral: true });
    db.prepare("UPDATE reservations SET status = 'confirmed', confirmed_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?").run(interaction.user.id, id);
    const embed = baseEmbed('✅ تأكيد حجز', 0x2ecc71).setDescription(`تم تأكيد طلب الحجز **#${id}** (${reservation.type}) بواسطة ${interaction.user}`);
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);
    const requester = await client.users.fetch(reservation.requested_by).catch(() => null);
    if (requester) await requester.send({ embeds: [embed] }).catch(() => {});
  }

  // ------------------- /ربط -------------------
  else if (commandName === 'ربط') {
    const playerId = interaction.options.getString('رقم_اللاعب');
    updatePlayer(interaction.user.id, { player_id: playerId });
    await interaction.reply({ content: `✅ تم ربط حسابك بهوية اللاعب: **${playerId}**`, ephemeral: true });
  }

  // ------------------- /بطاقة -------------------
  else if (commandName === 'بطاقة') {
    const target = interaction.options.getUser('العضو') || interaction.user;
    const player = getPlayer(target.id);
    const job = JOBS[player.job];
    const embed = baseEmbed(`🪪 بطاقة ${target.username}`)
      .setThumbnail(target.displayAvatarURL())
      .addFields(
        { name: 'رقم اللاعب', value: player.player_id || 'غير مربوط', inline: true },
        { name: 'الحالة', value: player.active ? '🟢 مفعّل' : '🔴 غير مفعّل', inline: true },
        { name: 'النقاط', value: String(player.points), inline: true },
        { name: 'الوظيفة', value: job ? `${job.emoji} ${job.name}` : 'بدون وظيفة', inline: true },
        { name: 'الرتبة', value: job ? job.ranks[player.rank_index] || '-' : '-', inline: true }
      );

    // إن كان الربط بـ VRP مفعّلًا، أضف بيانات مباشرة من قاعدة بيانات السيرفر
    if (CONFIG.vrp.enabled && player.player_id) {
      const vrpData = await getVrpPlayerData(player.player_id);
      if (vrpData) {
        embed.addFields({ name: '💰 الرصيد (من السيرفر)', value: String(vrpData.money ?? 'غير متوفر'), inline: true });
      }
    }

    const records = db.prepare('SELECT * FROM records WHERE discord_id = ? ORDER BY id DESC LIMIT 5').all(target.id);
    if (records.length > 0) {
      embed.addFields({
        name: '🕓 آخر 5 أحداث في السجل',
        value: records.map((r) => `• [${r.type}] ${r.detail}`).join('\n').slice(0, 1024),
      });
    }
    await interaction.reply({ embeds: [embed] });
  }

  // ------------------- /نقاط -------------------
  else if (commandName === 'نقاط') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const op = interaction.options.getString('العملية');
    const member = interaction.options.getUser('العضو');
    const amount = interaction.options.getInteger('العدد');
    const reason = interaction.options.getString('السبب') || 'بدون سبب محدد';
    const player = getPlayer(member.id);
    const newPoints = op === 'add' ? player.points + amount : Math.max(0, player.points - amount);
    updatePlayer(member.id, { points: newPoints });
    addRecord(member.id, op === 'add' ? 'points_add' : 'points_sub', `${amount} نقطة - ${reason}`, interaction.user.id);

    const embed = baseEmbed(op === 'add' ? '➕ إضافة نقاط' : '➖ خصم نقاط', op === 'add' ? 0x2ecc71 : 0xe74c3c)
      .setDescription(`${op === 'add' ? 'تم إضافة' : 'تم خصم'} **${amount}** نقطة ${op === 'add' ? 'إلى' : 'من'} ${member}`)
      .addFields({ name: 'السبب', value: reason }, { name: 'الرصيد الجديد', value: String(newPoints) });
    await interaction.reply({ embeds: [embed] });
    await sendLog(embed);

    // تنبيه ترقية تلقائي عند بلوغ حد النقاط للرتبة التالية
    const job = JOBS[player.job];
    if (job) {
      const nextRankIndex = player.rank_index + 1;
      const requiredPoints = nextRankIndex * CONFIG.pointsPerRank;
      if (nextRankIndex < job.ranks.length && newPoints >= requiredPoints) {
        await interaction.followUp({
          content: `🎉 ${member} أصبح مؤهلاً للترقية إلى رتبة **${job.ranks[nextRankIndex]}** (استخدم أمر /رتب لتفعيلها).`,
        });
      }
    }
  }

  // ------------------- /تذاكر_اعداد -------------------
  else if (commandName === 'تذاكر_اعداد') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const category = interaction.options.getChannel('التصنيف');
    if (category) {
      db.prepare('INSERT INTO ticket_config (guild_id, category_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET category_id = excluded.category_id').run(
        interaction.guild.id,
        category.id
      );
    }
    const menu = new StringSelectMenuBuilder()
      .setCustomId('ticket_open_select')
      .setPlaceholder('اختر القسم المناسب لفتح تذكرة')
      .addOptions(
        { label: 'الدعم الفني', value: 'support', emoji: '🛠️' },
        { label: 'شكاوى', value: 'complaints', emoji: '📢' },
        { label: 'استفسارات التوظيف', value: 'jobs', emoji: '🧑‍💼' },
        { label: 'الإدارة العليا', value: 'management', emoji: '👑' }
      );
    const row = new ActionRowBuilder().addComponents(menu);
    const embed = baseEmbed('🎫 نظام التذاكر').setDescription('اختر القسم المناسب من القائمة أدناه لفتح تذكرة دعم.');
    await interaction.reply({ embeds: [embed], components: [row] });
  }
}

const DEPARTMENTS = {
  support: '🛠️ الدعم الفني',
  complaints: '📢 شكاوى',
  jobs: '🧑‍💼 استفسارات التوظيف',
  management: '👑 الإدارة العليا',
};

function ticketControlsRow() {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('ticket_claim').setLabel('استلام').setEmoji('🙋').setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId('ticket_transfer').setLabel('تحويل').setEmoji('🔀').setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId('ticket_close').setLabel('إغلاق').setEmoji('🔒').setStyle(ButtonStyle.Danger)
  );
}

// ===================================================================
// 9) معالجة القوائم المنسدلة (فتح تذكرة / تحويل تذكرة)
// ===================================================================
async function handleSelectMenu(interaction) {
  if (interaction.customId === 'ticket_open_select') {
    await interaction.deferReply({ ephemeral: true });
    const dept = interaction.values[0];
    const existing = db.prepare("SELECT * FROM tickets WHERE user_id = ? AND department = ? AND status != 'closed'").get(interaction.user.id, dept);
    if (existing) {
      return interaction.editReply({ content: `⚠️ لديك تذكرة مفتوحة بالفعل: <#${existing.channel_id}>` });
    }

    const guildCfg = db.prepare('SELECT * FROM ticket_config WHERE guild_id = ?').get(interaction.guild.id);
    const channel = await interaction.guild.channels.create({
      name: `ticket-${interaction.user.username}`.toLowerCase().slice(0, 90),
      type: ChannelType.GuildText,
      parent: guildCfg?.category_id || undefined,
      permissionOverwrites: [
        { id: interaction.guild.roles.everyone.id, deny: [PermissionFlagsBits.ViewChannel] },
        { id: interaction.user.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory] },
        ...(CONFIG.adminRoleId ? [{ id: CONFIG.adminRoleId, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory] }] : []),
      ],
    });

    db.prepare('INSERT INTO tickets (channel_id, user_id, department) VALUES (?, ?, ?)').run(channel.id, interaction.user.id, dept);

    const embed = baseEmbed(`🎫 تذكرة جديدة - ${DEPARTMENTS[dept]}`)
      .setDescription(`مرحبًا ${interaction.user}!\nيرجى وصف مشكلتك أو طلبك بالتفصيل وسيقوم أحد المسؤولين بالرد عليك قريبًا.`);
    await channel.send({ content: `${interaction.user}`, embeds: [embed], components: [ticketControlsRow()] });

    await interaction.editReply({ content: `✅ تم فتح تذكرتك: ${channel}` });
  }

  else if (interaction.customId === 'ticket_transfer_select') {
    const ticket = db.prepare('SELECT * FROM tickets WHERE channel_id = ?').get(interaction.channel.id);
    if (!ticket) return interaction.reply({ content: '❌ هذه ليست قناة تذكرة.', ephemeral: true });
    const newDept = interaction.values[0];
    db.prepare('UPDATE tickets SET department = ? WHERE channel_id = ?').run(newDept, interaction.channel.id);
    await interaction.reply({ embeds: [baseEmbed('🔀 تحويل التذكرة', 0xf39c12).setDescription(`تم تحويل التذكرة إلى قسم: **${DEPARTMENTS[newDept]}**`)] });
  }
}

// ===================================================================
// 10) معالجة الأزرار (استلام / تحويل / إغلاق التذكرة)
// ===================================================================
async function handleButton(interaction) {
  const ticket = db.prepare('SELECT * FROM tickets WHERE channel_id = ?').get(interaction.channel.id);
  if (!ticket) return interaction.reply({ content: '❌ هذه ليست قناة تذكرة صالحة.', ephemeral: true });

  if (interaction.customId === 'ticket_claim') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    db.prepare("UPDATE tickets SET status = 'claimed', claimed_by = ? WHERE channel_id = ?").run(interaction.user.id, interaction.channel.id);
    await interaction.reply({ embeds: [baseEmbed('🙋 تم استلام التذكرة', 0x3498db).setDescription(`تم استلام هذه التذكرة بواسطة ${interaction.user}`)] });
  }

  else if (interaction.customId === 'ticket_transfer') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    const menu = new StringSelectMenuBuilder()
      .setCustomId('ticket_transfer_select')
      .setPlaceholder('اختر القسم الجديد')
      .addOptions(Object.entries(DEPARTMENTS).map(([value, label]) => ({ label, value })));
    await interaction.reply({ content: 'اختر القسم الذي تريد تحويل التذكرة إليه:', components: [new ActionRowBuilder().addComponents(menu)], ephemeral: true });
  }

  else if (interaction.customId === 'ticket_close') {
    if (!isAdmin(interaction)) return denyNotAdmin(interaction);
    await interaction.reply('🔒 يتم الآن إغلاق التذكرة وحفظ نسخة من المحادثة...');

    // بناء transcript نصي بسيط من آخر 100 رسالة
    const messages = await interaction.channel.messages.fetch({ limit: 100 });
    const sorted = [...messages.values()].reverse();
    const lines = sorted.map((m) => `[${m.createdAt.toISOString()}] ${m.author.tag}: ${m.content}`);
    const transcriptText = lines.join('\n') || 'لا توجد رسائل.';
    const attachment = new AttachmentBuilder(Buffer.from(transcriptText, 'utf-8'), { name: `transcript-${ticket.id}.txt` });

    db.prepare("UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP WHERE channel_id = ?").run(interaction.channel.id);

    if (CONFIG.ticketLogChannelId) {
      const logChannel = await client.channels.fetch(CONFIG.ticketLogChannelId).catch(() => null);
      if (logChannel) {
        const embed = baseEmbed('🔒 تم إغلاق تذكرة', 0xe74c3c).addFields(
          { name: 'صاحب التذكرة', value: `<@${ticket.user_id}>`, inline: true },
          { name: 'القسم', value: DEPARTMENTS[ticket.department] || ticket.department, inline: true },
          { name: 'أُغلقت بواسطة', value: `${interaction.user}`, inline: true }
        );
        await logChannel.send({ embeds: [embed], files: [attachment] }).catch(() => {});
      }
    }

    setTimeout(() => {
      interaction.channel.delete().catch(() => {});
    }, 5000);
  }
}

// ===================================================================
// 11) تسجيل الدخول
// ===================================================================
client.login(CONFIG.token);


{
  "name": "rp-server-bot",
  "version": "1.0.0",
  "description": "بوت ديسكورد لإدارة سيرفر رول بلاي (FiveM) - ملف واحد",
  "main": "index.js",
  "type": "commonjs",
  "scripts": {
    "start": "node index.js"
  },
  "dependencies": {
    "discord.js": "^14.16.3",
    "better-sqlite3": "^11.3.0",
    "mysql2": "^3.11.3",
    "dotenv": "^16.4.5"
  }
}
