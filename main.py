import os
import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "+"

MIN_ACCOUNT_AGE_DAYS = 2
RAID_JOIN_THRESHOLD = 5
RAID_JOIN_WINDOW = 10
RAID_AUTO_LOCKDOWN = True
RAID_AUTO_ACTION = "kick"  # "kick", "ban" ou "none" pour les joins pendant un raid
RAID_COOLDOWN = 300  # duree (s) pendant laquelle le mode raid reste actif
BOT_WHITELIST = set()

BLACKLIST_FILE = "blacklist.json"
RAID_LOG_CHANNEL_NAME = "mod-logs"

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
raid_mode = {}          # guild.id -> timestamp de debut du raid
locked_channels = {}    # guild.id -> set de channel.id verrouilles automatiquement


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
    """Verrouille tous les salons textuels et memorise lesquels on a touches."""
    locked = set()
    for ch in guild.text_channels:
        try:
            ow = ch.overwrites_for(guild.default_role)
            if ow.send_messages is False:
                continue  # deja verrouille, on ne le touche pas
            ow.send_messages = False
            await ch.set_permissions(guild.default_role, overwrite=ow, reason=reason)
            locked.add(ch.id)
        except discord.Forbidden:
            pass
    locked_channels[guild.id] = locked
    await log_action(guild, f"AUTO-LOCKDOWN ({len(locked)} salons) - {reason}")


async def auto_unlockdown(guild, reason):
    """Deverrouille uniquement les salons verrouilles par l'auto-lockdown."""
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
    print(f"Prefixe : {PREFIX}")
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
                f"Ban auto : {member} - compte cree il y a {account_age.days}j "
                f"({member.created_at:%Y-%m-%d})"
            )
            return
        except discord.Forbidden:
            await log_action(guild, f"Ban impossible sur {member}")

    # --- Anti-raid ---
    q = recent_joins.setdefault(guild.id, deque())
    q.append(time.time())
    while q and time.time() - q[0] > RAID_JOIN_WINDOW:
        q.popleft()

    # Si un raid est deja en cours, on applique l'action automatique aux nouveaux arrivants
    if raid_active(guild.id):
        try:
            if RAID_AUTO_ACTION == "ban":
                await member.ban(reason="Raid en cours", delete_message_days=0)
                await log_action(guild, f"[RAID] Ban auto : {member} ({member.id})")
            elif RAID_AUTO_ACTION == "kick":
                await member.kick(reason="Raid en cours")
                await log_action(guild, f"[RAID] Kick auto : {member} ({member.id})")
        except discord.Forbidden:
            await log_action(guild, f"[RAID] Action impossible sur {member}")
        return

    # Declenchement d'un raid
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


def is_mod():
    async def predicate(ctx):
        return ctx.author.guild_permissions.manage_messages
    return commands.check(predicate)


def is_admin():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)


@bot.group(invoke_without_command=True, name="blacklist")
@is_mod()
async def blacklist_cmd(ctx):
    if not blacklist:
        await ctx.send("Blacklist vide.")
    else:
        await ctx.send("Blacklist : " + ", ".join(f"`{w}`" for w in sorted(blacklist)))


@blacklist_cmd.command(name="add")
@is_mod()
async def bl_add(ctx, *, word):
    blacklist.add(word.lower())
    save_blacklist(blacklist)
    await ctx.send(f"`{word}` ajoute a la blacklist.")


@blacklist_cmd.command(name="remove")
@is_mod()
async def bl_remove(ctx, *, word):
    blacklist.discard(word.lower())
    save_blacklist(blacklist)
    await ctx.send(f"`{word}` retire de la blacklist.")


@bot.command()
@is_mod()
async def lock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite,
                                  reason=f"Lock par {ctx.author}")
    await ctx.send(f"{channel.mention} verrouille.")
    await log_action(ctx.guild, f"{channel.mention} lock par {ctx.author}")


@bot.command()
@is_mod()
async def unlock(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    overwrite = channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite,
                                  reason=f"Unlock par {ctx.author}")
    await ctx.send(f"{channel.mention} deverrouille.")
    await log_action(ctx.guild, f"{channel.mention} unlock par {ctx.author}")


@bot.command()
@is_mod()
async def lockall(ctx):
    count = 0
    for ch in ctx.guild.text_channels:
        try:
            ow = ch.overwrites_for(ctx.guild.default_role)
            ow.send_messages = False
            await ch.set_permissions(ctx.guild.default_role, overwrite=ow,
                                     reason=f"Lockdown par {ctx.author}")
            count += 1
        except discord.Forbidden:
            pass
    await ctx.send(f"Lockdown : {count} salons verrouilles.")
    await log_action(ctx.guild, f"LOCKDOWN total par {ctx.author} ({count} salons)")


@bot.command()
@is_mod()
async def unlockall(ctx):
    count = 0
    for ch in ctx.guild.text_channels:
        try:
            ow = ch.overwrites_for(ctx.guild.default_role)
            ow.send_messages = None
            await ch.set_permissions(ctx.guild.default_role, overwrite=ow,
                                     reason=f"Fin lockdown par {ctx.author}")
            count += 1
        except discord.Forbidden:
            pass
    raid_mode.pop(ctx.guild.id, None)
    locked_channels.pop(ctx.guild.id, None)
    await ctx.send(f"{count} salons deverrouilles.")
    await log_action(ctx.guild, f"Fin du lockdown par {ctx.author} ({count} salons)")


# --- Commandes anti-raid manuelles ---

@bot.command(name="raid")
@is_admin()
async def raid_status(ctx):
    """Affiche l'etat du mode anti-raid."""
    if raid_active(ctx.guild.id):
        since = int(time.time() - raid_mode[ctx.guild.id])
        await ctx.send(f"Mode raid ACTIF depuis {since}s (action : {RAID_AUTO_ACTION}).")
    else:
        await ctx.send("Mode raid inactif.")


@bot.command(name="raidon")
@is_admin()
async def raid_on(ctx):
    """Active manuellement le mode anti-raid + lockdown."""
    raid_mode[ctx.guild.id] = time.time()
    await ctx.send(f"Mode raid ACTIVE manuellement ({RAID_AUTO_ACTION}).")
    await log_action(ctx.guild, f"Mode raid active manuellement par {ctx.author}")
    if RAID_AUTO_LOCKDOWN:
        await auto_lockdown(ctx.guild, reason=f"Anti-raid manuel ({ctx.author})")


@bot.command(name="raidoff")
@is_admin()
async def raid_off(ctx):
    """Desactive le mode anti-raid et deverrouille les salons auto."""
    raid_mode.pop(ctx.guild.id, None)
    await auto_unlockdown(ctx.guild, reason=f"Fin raid manuelle ({ctx.author})")
    await ctx.send("Mode raid DESACTIVE.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("Tu n'as pas les permissions.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Argument manquant : `{error.param.name}`")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"Erreur : `{error}`")
        raise error


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Variable d'environnement DISCORD_TOKEN manquante.")
    bot.run(TOKEN)
