import os
import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "/"

MIN_ACCOUNT_AGE_DAYS = 2
RAID_JOIN_THRESHOLD = 8
RAID_JOIN_WINDOW = 10
RAID_AUTO_LOCKDOWN = True
RAID_AUTO_ACTION = "kick"
RAID_COOLDOWN = 300
RAID_SUSPICIOUS_AGE_DAYS = 30  # pendant un raid, on ne touche qu'aux comptes plus jeunes que ca
RAID_COUNT_ONLY_YOUNG = True   # seuls les comptes < RAID_SUSPICIOUS_AGE_DAYS comptent dans le seuil
BOT_WHITELIST = set()

BLACKLIST_FILE = "blacklist.json"
RAID_LOG_CHANNEL_NAME = "mod-logs"
AUTOROLE_NAME = "Membres Guerilla 🏳️"
AUTOROLE_ID = None  # remplace par l'ID du role (ex: 1234567890) pour un match 100% fiable

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


def load_blacklist():
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_blacklist(words):
    with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(words), f, ensure_ascii=False, indent=2)


blacklist = load_blacklist()
recent_joins = {}
raid_mode = {}
locked_channels = {}


async def get_log_channel(guild):
    return discord.utils.get(guild.text_channels, name=RAID_LOG_CHANNEL_NAME)


async def log_action(guild, msg):
    ch = await get_log_channel(guild)
    if ch:
        try:
            await ch.send(msg)
        except discord.Forbidden:
            pass
    print(f"[{guild.name}] {msg}")


async def auto_lockdown(guild, reason):
    locked = set()
    for ch in guild.text_channels:
        try:
            ow = ch.overwrites_for(guild.default_role)
            if ow.send_messages is False:
                continue
            ow.send_messages = False
            await ch.set_permissions(guild.default_role, overwrite=ow, reason=reason)
            locked.add(ch.id)
        except discord.Forbidden:
            pass
    locked_channels[guild.id] = locked
    await log_action(guild, f"AUTO-LOCKDOWN ({len(locked)} salons) - {reason}")


async def auto_unlockdown(guild, reason):
    ids = locked_channels.pop(guild.id, set())
    count = 0
    for ch_id in ids:
        ch = guild.get_channel(ch_id)
        if ch is None:
            continue
        try:
            ow = ch.overwrites_for(guild.default_role)
            ow.send_messages = None
            await ch.set_permissions(guild.default_role, overwrite=ow, reason=reason)
            count += 1
        except discord.Forbidden:
            pass
    await log_action(guild, f"FIN AUTO-LOCKDOWN ({count} salons) - {reason}")


def _normalize(s: str) -> str:
    return "".join(c for c in (s or "") if c != "️").casefold().strip()


def find_autorole(guild):
    if AUTOROLE_ID:
        r = guild.get_role(AUTOROLE_ID)
        if r:
            return r
    target = _normalize(AUTOROLE_NAME)
    for r in guild.roles:
        if _normalize(r.name) == target:
            return r
    return None


def raid_active(guild_id):
    started = raid_mode.get(guild_id)
    if not started:
        return False
    if time.time() - started > RAID_COOLDOWN:
        raid_mode.pop(guild_id, None)
        return False
    return True


@bot.event
async def on_ready():
    print(f"Connecte en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Slash commands synchronisees : {len(synced)}")
    except Exception as e:
        print(f"Erreur sync slash : {e}")
    print(f"Serveurs : {len(bot.guilds)}")


@bot.event
async def on_member_join(member):
    guild = member.guild
    now = datetime.now(timezone.utc)

    if member.bot and member.id not in BOT_WHITELIST:
        try:
            await member.kick(reason="Bot non autorise")
            await log_action(guild, f"Bot kicke automatiquement : {member} ({member.id})")
        except discord.Forbidden:
            await log_action(guild, f"Impossible de kick le bot {member}")
        return

    account_age = now - member.created_at
    if account_age < timedelta(days=MIN_ACCOUNT_AGE_DAYS):
        try:
            try:
                await member.send(
                    f"Ton compte est trop recent (< {MIN_ACCOUNT_AGE_DAYS} jours) "
                    f"pour rejoindre {guild.name}."
                )
            except discord.Forbidden:
                pass
            await member.ban(
                reason=f"Compte cree il y a {account_age.days}j",
                delete_message_days=0,
            )
            await log_action(
                guild,
                f"Ban auto : {member} - compte cree il y a {account_age.days}j"
            )
            return
        except discord.Forbidden:
            await log_action(guild, f"Ban impossible sur {member}")

    role = find_autorole(guild)
    if role is None:
        noms = ", ".join(repr(r.name) for r in guild.roles if "guerilla" in r.name.lower())
        await log_action(
            guild,
            f"Auto-role : role '{AUTOROLE_NAME}' introuvable. "
            f"Roles contenant 'guerilla' : {noms or 'aucun'}"
        )
    elif role >= guild.me.top_role:
        await log_action(
            guild,
            f"Auto-role : le role '{role.name}' est AU-DESSUS du role du bot "
            f"({guild.me.top_role.name}). Remonte le role du bot dans la hierarchie."
        )
    elif not guild.me.guild_permissions.manage_roles:
        await log_action(guild, "Auto-role : permission 'Gerer les roles' manquante sur le bot.")
    else:
        try:
            await member.add_roles(role, reason="Auto-role a l'arrivee")
        except discord.Forbidden:
            await log_action(guild, f"Auto-role refuse sur {member} (Forbidden)")
        except discord.HTTPException as e:
            await log_action(guild, f"Auto-role echoue sur {member} : {e}")

    is_young = account_age < timedelta(days=RAID_SUSPICIOUS_AGE_DAYS)

    q = recent_joins.setdefault(guild.id, deque())
    if is_young or not RAID_COUNT_ONLY_YOUNG:
        q.append(time.time())
    while q and time.time() - q[0] > RAID_JOIN_WINDOW:
        q.popleft()

    if raid_active(guild.id):
        if not is_young:
            await log_action(
                guild,
                f"[RAID] {member} epargne (compte de {account_age.days}j)"
            )
        else:
            try:
                if RAID_AUTO_ACTION == "ban":
                    await member.ban(reason="Raid en cours", delete_message_days=0)
                    await log_action(guild, f"[RAID] Ban auto : {member} ({account_age.days}j)")
                elif RAID_AUTO_ACTION == "kick":
                    await member.kick(reason="Raid en cours")
                    await log_action(guild, f"[RAID] Kick auto : {member} ({account_age.days}j)")
            except discord.Forbidden:
                await log_action(guild, f"[RAID] Action impossible sur {member}")
            return

    if len(q) >= RAID_JOIN_THRESHOLD:
        raid_mode[guild.id] = time.time()
        await log_action(
            guild,
            f"RAID DETECTE - {len(q)} joins en {RAID_JOIN_WINDOW}s. "
            f"Action auto : {RAID_AUTO_ACTION}."
        )
        if RAID_AUTO_LOCKDOWN:
            await auto_lockdown(guild, reason="Anti-raid automatique")


@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    content_lower = message.content.lower()
    if any(word in content_lower for word in blacklist):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} mot interdit detecte.",
                delete_after=5,
            )
            await log_action(
                message.guild,
                f"Message supprime de {message.author} : {message.content[:80]}"
            )
        except discord.Forbidden:
            pass
        return

    await bot.process_commands(message)


def mod_check(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.manage_messages


def admin_check(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


@bot.tree.command(name="clear", description="Supprime un nombre de messages dans le salon")
@app_commands.describe(amount="Nombre de messages a supprimer (1-1000)")
async def clear(interaction: discord.Interaction, amount: int):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    if amount < 1 or amount > 1000:
        await interaction.response.send_message("Donne un nombre entre 1 et 1000.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"{len(deleted)} messages supprimes.", ephemeral=True)
        await log_action(
            interaction.guild,
            f"{interaction.user} a clear {len(deleted)} messages dans {interaction.channel.mention}"
        )
    except discord.Forbidden:
        await interaction.followup.send("Permissions manquantes pour supprimer.", ephemeral=True)


@bot.tree.command(name="lock", description="Verrouille un salon")
@app_commands.describe(channel="Salon a verrouiller (celui courant par defaut)")
async def lock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    channel = channel or interaction.channel
    ow = channel.overwrites_for(interaction.guild.default_role)
    ow.send_messages = False
    await channel.set_permissions(interaction.guild.default_role, overwrite=ow,
                                  reason=f"Lock par {interaction.user}")
    await interaction.response.send_message(f"{channel.mention} verrouille.")
    await log_action(interaction.guild, f"{channel.mention} lock par {interaction.user}")


@bot.tree.command(name="unlock", description="Deverrouille un salon")
@app_commands.describe(channel="Salon a deverrouiller")
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    channel = channel or interaction.channel
    ow = channel.overwrites_for(interaction.guild.default_role)
    ow.send_messages = None
    await channel.set_permissions(interaction.guild.default_role, overwrite=ow,
                                  reason=f"Unlock par {interaction.user}")
    await interaction.response.send_message(f"{channel.mention} deverrouille.")
    await log_action(interaction.guild, f"{channel.mention} unlock par {interaction.user}")


@bot.tree.command(name="lockall", description="Verrouille tous les salons")
async def lockall(interaction: discord.Interaction):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = False
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow,
                                     reason=f"Lockdown par {interaction.user}")
            count += 1
        except discord.Forbidden:
            pass
    await interaction.followup.send(f"Lockdown : {count} salons verrouilles.")
    await log_action(interaction.guild, f"LOCKDOWN total par {interaction.user} ({count} salons)")


@bot.tree.command(name="unlockall", description="Deverrouille tous les salons")
async def unlockall(interaction: discord.Interaction):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    await interaction.response.defer()
    count = 0
    for ch in interaction.guild.text_channels:
        try:
            ow = ch.overwrites_for(interaction.guild.default_role)
            ow.send_messages = None
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow,
                                     reason=f"Fin lockdown par {interaction.user}")
            count += 1
        except discord.Forbidden:
            pass
    raid_mode.pop(interaction.guild.id, None)
    locked_channels.pop(interaction.guild.id, None)
    await interaction.followup.send(f"{count} salons deverrouilles.")
    await log_action(interaction.guild, f"Fin du lockdown par {interaction.user} ({count} salons)")


blacklist_group = app_commands.Group(name="blacklist", description="Gestion de la blacklist")


@blacklist_group.command(name="list", description="Affiche la blacklist")
async def bl_list(interaction: discord.Interaction):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    if not blacklist:
        await interaction.response.send_message("Blacklist vide.")
    else:
        await interaction.response.send_message(
            "Blacklist : " + ", ".join(f"`{w}`" for w in sorted(blacklist))
        )


@blacklist_group.command(name="add", description="Ajoute un mot a la blacklist")
@app_commands.describe(word="Mot a ajouter")
async def bl_add(interaction: discord.Interaction, word: str):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    blacklist.add(word.lower())
    save_blacklist(blacklist)
    await interaction.response.send_message(f"`{word}` ajoute a la blacklist.")


@blacklist_group.command(name="remove", description="Retire un mot de la blacklist")
@app_commands.describe(word="Mot a retirer")
async def bl_remove(interaction: discord.Interaction, word: str):
    if not mod_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    blacklist.discard(word.lower())
    save_blacklist(blacklist)
    await interaction.response.send_message(f"`{word}` retire de la blacklist.")


bot.tree.add_command(blacklist_group)


@bot.tree.command(name="raid", description="Etat du mode anti-raid")
async def raid_status(interaction: discord.Interaction):
    if not admin_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    if raid_active(interaction.guild.id):
        since = int(time.time() - raid_mode[interaction.guild.id])
        await interaction.response.send_message(
            f"Mode raid ACTIF depuis {since}s (action : {RAID_AUTO_ACTION})."
        )
    else:
        await interaction.response.send_message("Mode raid inactif.")


@bot.tree.command(name="raidon", description="Active manuellement le mode anti-raid")
async def raid_on(interaction: discord.Interaction):
    if not admin_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    raid_mode[interaction.guild.id] = time.time()
    await interaction.response.send_message(f"Mode raid ACTIVE ({RAID_AUTO_ACTION}).")
    await log_action(interaction.guild, f"Mode raid active manuellement par {interaction.user}")
    if RAID_AUTO_LOCKDOWN:
        await auto_lockdown(interaction.guild, reason=f"Anti-raid manuel ({interaction.user})")


@bot.tree.command(name="raidoff", description="Desactive le mode anti-raid")
async def raid_off(interaction: discord.Interaction):
    if not admin_check(interaction):
        await interaction.response.send_message("Permissions manquantes.", ephemeral=True)
        return
    raid_mode.pop(interaction.guild.id, None)
    await auto_unlockdown(interaction.guild, reason=f"Fin raid manuelle ({interaction.user})")
    await interaction.response.send_message("Mode raid DESACTIVE.")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Variable d'environnement DISCORD_TOKEN manquante.")
    bot.run(TOKEN)
